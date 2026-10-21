"""
Tests for the Kafka pipeline, with fake Kafka clients (no broker needed).

Message processing is checked against a real Postgres when
TEST_DATABASE_URL is set; the rest runs anywhere.
"""

import contextlib
import io
import os
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from api.routes.score import ScoreRequest
from kafka_pipeline import consumer, producer

TEST_DB = os.getenv("TEST_DATABASE_URL")


class FakeProducer:
    def __init__(self, *args, **kwargs):
        self.sent = []
        self.flushed = self.closed = False

    def send(self, topic, key=None, value=None):
        self.sent.append((topic, key, value))

    def flush(self):
        self.flushed = True

    def close(self):
        self.closed = True


class FakeConsumer:
    """Delivers messages in order; seek() re-delivers one, like Kafka."""

    def __init__(self, messages):
        self.pending = list(messages)
        self.by_offset = {m.offset: m for m in messages}
        self.commits = 0
        self.seeks = []
        self.closed = False

    def __iter__(self):
        while self.pending:
            yield self.pending.pop(0)

    def seek(self, partition, offset):
        self.seeks.append(offset)
        self.pending.insert(0, self.by_offset[offset])

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def quietly(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def message(**overrides):
    body = {
        "transaction_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "merchant_id": str(producer.MERCHANTS[0]),
        "amount_cents": 4_500,
        "currency": "USD",
        "country_code": "US",
        "occurred_at": "2026-06-06T13:00:00+00:00",
        "lat": 40.7128,
        "lon": -74.0060,
    }
    body.update(overrides)
    return body


# ─── Producer ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("high_risk", [False, True])
def test_generated_transactions_are_valid_score_requests(high_risk):
    for _ in range(50):
        txn = producer.make_transaction(uuid.uuid4(), high_risk=high_risk)
        ScoreRequest(**txn)  # raises if the payload wouldn't pass the API
        hour = datetime.fromisoformat(txn["occurred_at"]).hour
        if high_risk:
            assert 500_00 <= txn["amount_cents"] <= 10_000_00 and hour in (1, 2, 3, 4)
        else:
            assert 10_00 <= txn["amount_cents"] <= 500_00 and 9 <= hour <= 18


def test_produce_publishes_keyed_by_user(monkeypatch):
    fake = FakeProducer()
    monkeypatch.setattr(producer, "KafkaProducer", lambda **kw: fake)
    quietly(producer.produce, count=12, high_risk_pct=0.5)

    assert len(fake.sent) == 12
    for topic, key, value in fake.sent:
        assert topic == producer.TOPIC
        assert key == value["user_id"]  # same user, same partition
    assert fake.flushed and fake.closed


@pytest.mark.parametrize(
    "score,expected", [(0.95, "high"), (0.8, "high"), (0.7, "medium"), (0.45, "low")]
)
def test_severity_matches_the_api(score, expected):
    from api.routes.score import map_severity

    assert consumer.map_severity(score) == expected == map_severity(score)


# ─── Consumer loop ────────────────────────────────────────────────────────────


def _run_with(monkeypatch, msgs, process):
    fake_consumer, fake_producer = FakeConsumer(msgs), FakeProducer()
    sleeps = []
    monkeypatch.setattr(consumer, "load_model", lambda: None)
    monkeypatch.setattr(consumer, "get_engine", lambda: None)
    monkeypatch.setattr(consumer, "Session", lambda engine: contextlib.nullcontext())
    monkeypatch.setattr(consumer, "KafkaConsumer", lambda *a, **kw: fake_consumer)
    monkeypatch.setattr(consumer, "KafkaProducer", lambda **kw: fake_producer)
    monkeypatch.setattr(consumer, "process_message", process)
    monkeypatch.setattr(consumer.time, "sleep", sleeps.append)
    quietly(consumer.run)
    return fake_consumer, fake_producer, sleeps


def kafka_message(offset):
    return SimpleNamespace(
        topic="transactions.raw", partition=0, offset=offset, value=message()
    )


def test_bad_message_is_skipped_without_blocking_the_queue(monkeypatch):
    processed = []

    def process(msg, offset, db, prod):
        if offset == 1:
            raise ValueError("malformed payload")
        processed.append(offset)

    fake_consumer, fake_producer, sleeps = _run_with(
        monkeypatch, [kafka_message(i) for i in range(3)], process
    )
    assert processed == [0, 2]
    assert fake_consumer.commits == 3  # bad message committed past, not retried
    assert fake_consumer.seeks == [] and sleeps == []
    assert fake_consumer.closed and fake_producer.closed


def test_database_outage_retries_the_same_message_instead_of_losing_it(monkeypatch):
    from sqlalchemy.exc import OperationalError

    processed = []
    outage = {"remaining": 3}

    def process(msg, offset, db, prod):
        if offset == 1 and outage["remaining"]:
            outage["remaining"] -= 1
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        processed.append(offset)

    fake_consumer, _, sleeps = _run_with(
        monkeypatch, [kafka_message(i) for i in range(3)], process
    )
    assert processed == [0, 1, 2]  # message 1 eventually processed, in order
    assert fake_consumer.seeks == [1, 1, 1]  # rewound once per failed attempt
    assert sleeps == [1, 2, 4]  # exponential backoff
    assert fake_consumer.commits == 3  # never committed past the failure


def test_backoff_is_capped(monkeypatch):
    from sqlalchemy.exc import OperationalError

    outage = {"remaining": 8}

    def process(msg, offset, db, prod):
        if outage["remaining"]:
            outage["remaining"] -= 1
            raise OperationalError("SELECT 1", {}, Exception("down"))

    _, _, sleeps = _run_with(monkeypatch, [kafka_message(0)], process)
    assert sleeps == [1, 2, 4, 8, 16, 30, 30, 30]


# ─── Message processing (Postgres) ────────────────────────────────────────────


@pytest.fixture
def db(monkeypatch):
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL not set")
    from db import models
    from ml import predict
    from sqlalchemy.orm import Session

    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    models.get_engine.cache_clear()
    engine = models.get_engine()
    models.Base.metadata.drop_all(engine)
    models.Base.metadata.create_all(engine)
    quietly(predict.load_model)
    with Session(engine) as session:
        yield session
    engine.dispose()
    models.get_engine.cache_clear()


@pytest.mark.integration
def test_risky_message_is_stored_flagged_and_published(db):
    from db.models import FraudAlert, FraudScore, Transaction

    fake = FakeProducer()
    msg = message(amount_cents=300_000, occurred_at="2026-06-06T03:00:00+00:00")
    quietly(consumer.process_message, msg, 42, db, fake)

    txn = db.get(Transaction, uuid.UUID(msg["transaction_id"]))
    assert txn.status == "flagged" and txn.kafka_offset == 42
    assert db.query(FraudScore).one().model_version == "xgb-v2.0.0"
    assert db.query(FraudAlert).one().state == "open"

    [(topic, key, event)] = fake.sent
    assert topic == consumer.TOPIC_SCORED and key == msg["user_id"]
    assert (
        event["verdict"] == "flagged"
        and event["transaction_id"] == msg["transaction_id"]
    )


@pytest.mark.integration
def test_ordinary_message_is_approved_without_alert(db):
    from db.models import FraudAlert, Transaction

    fake = FakeProducer()
    msg = message()
    quietly(consumer.process_message, msg, 7, db, fake)

    assert db.get(Transaction, uuid.UUID(msg["transaction_id"])).status == "approved"
    assert db.query(FraudAlert).count() == 0
    assert fake.sent[0][2]["verdict"] == "approved"


@pytest.mark.integration
def test_redelivered_message_is_not_scored_twice(db):
    from db.models import FraudScore

    fake = FakeProducer()
    msg = message()
    quietly(consumer.process_message, msg, 7, db, fake)
    quietly(consumer.process_message, msg, 7, db, fake)  # Kafka redelivery

    assert db.query(FraudScore).count() == 1
    assert len(fake.sent) == 1


def test_generated_timestamps_are_never_in_the_future(monkeypatch):
    early_morning = datetime(2026, 6, 6, 0, 30, tzinfo=producer.UTC)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return early_morning

    monkeypatch.setattr(producer, "datetime", FrozenDatetime)
    for high_risk in (True, False):
        for _ in range(20):
            txn = producer.make_transaction(uuid.uuid4(), high_risk=high_risk)
            assert datetime.fromisoformat(txn["occurred_at"]) <= early_morning
