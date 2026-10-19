"""
End-to-end API tests against a real Postgres.

Skipped unless TEST_DATABASE_URL is set. All tables in that database are
dropped and recreated for every test, so point it at a throwaway database:

    TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/fraud_test pytest tests/
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

TEST_DB = os.getenv("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not TEST_DB, reason="TEST_DATABASE_URL not set"),
]


@pytest.fixture
def client(monkeypatch):
    from db import models
    from main import app
    from ml import predict

    monkeypatch.setenv("DATABASE_URL", TEST_DB)
    models.get_engine.cache_clear()
    engine = models.get_engine()
    models.Base.metadata.drop_all(engine)
    models.Base.metadata.create_all(engine)
    predict.load_model()
    yield TestClient(app)
    engine.dispose()
    models.get_engine.cache_clear()


@pytest.fixture
def session():
    from db.models import get_engine
    from sqlalchemy.orm import Session

    with Session(get_engine()) as s:
        yield s


def score(client, **overrides):
    body = {
        "transaction_id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "amount_cents": 125_000,
        "currency": "USD",
        "country_code": "US",
        "ip_address": "203.0.113.7",
        "occurred_at": "2026-06-06T14:00:00Z",
    }
    body.update(overrides)
    return client.post("/v1/score", json=body)


def always(monkeypatch, verdict):
    """Pin the threshold so the model's score decides nothing in this test."""
    from ml import predict

    monkeypatch.setattr(predict, "THRESHOLD", 0.0 if verdict == "flagged" else 1.01)


def test_approved_transaction_is_stored_without_an_alert(client, session, monkeypatch):
    from db.models import FraudAlert, FraudScore, Transaction

    always(monkeypatch, "approved")
    res = score(client)
    assert res.status_code == 200
    body = res.json()
    assert body["verdict"] == "approved" and body["severity"] is None
    assert 0.0 <= body["score"] <= 1.0
    assert body["features"]

    txn = session.get(Transaction, uuid.UUID(body["transaction_id"]))
    assert txn.status == "approved" and str(txn.ip_address) == "203.0.113.7"
    assert session.query(FraudScore).count() == 1
    assert session.query(FraudAlert).count() == 0


def test_flagged_transaction_raises_an_alert(client, monkeypatch):
    always(monkeypatch, "flagged")
    body = score(client).json()
    assert body["verdict"] == "flagged"

    alerts = client.get("/v1/alerts").json()
    assert alerts["total"] == 1
    alert = alerts["alerts"][0]
    assert alert["transaction_id"] == body["transaction_id"]
    assert alert["state"] == "open" and alert["severity"] == body["severity"]

    sla = datetime.fromisoformat(alert["sla_deadline"])
    assert (
        timedelta(hours=3, minutes=59) < sla - datetime.now(UTC) <= timedelta(hours=4)
    )

    detail = client.get(f"/v1/alerts/{alert['alert_id']}").json()
    assert detail["amount_cents"] == 125_000 and detail["country_code"] == "US"
    assert 0 < len(detail["top_features"]) <= 5


def test_ipv6_addresses_are_stored(client, session, monkeypatch):
    from db.models import Transaction

    always(monkeypatch, "approved")
    body = score(client, ip_address="2001:db8::1").json()
    txn = session.get(Transaction, uuid.UUID(body["transaction_id"]))
    assert str(txn.ip_address) == "2001:db8::1"


def test_rescoring_a_transaction_is_a_conflict(client, monkeypatch):
    always(monkeypatch, "approved")
    txn_id = str(uuid.uuid4())
    assert score(client, transaction_id=txn_id).status_code == 200
    assert score(client, transaction_id=txn_id).status_code == 409


def test_race_on_duplicate_insert_is_a_conflict_not_a_crash(
    client, session, monkeypatch
):
    """
    Simulates the race: another request inserted the transaction after our
    duplicate check ran. Previously this surfaced as a 500.
    """
    from db.models import FraudScore, Transaction

    always(monkeypatch, "approved")
    txn_id = uuid.uuid4()
    session.add(
        Transaction(
            id=txn_id,
            user_id=uuid.uuid4(),
            amount_cents=1,
            currency="USD",
            occurred_at=datetime.now(UTC),
        )
    )
    session.commit()

    res = score(client, transaction_id=str(txn_id))
    assert res.status_code == 409
    assert session.query(FraudScore).count() == 0  # nothing half-written


def test_review_closes_alert_once(client, session, monkeypatch):
    from db.models import FraudAlert, ReviewerFeedback

    always(monkeypatch, "flagged")
    score(client)
    alert_id = client.get("/v1/alerts").json()["alerts"][0]["alert_id"]

    res = client.patch(
        f"/v1/alerts/{alert_id}/review",
        json={"verdict": "confirmed", "notes": "card reported stolen"},
    )
    assert res.status_code == 200
    assert res.json()["state"] == "closed"

    again = client.patch(
        f"/v1/alerts/{alert_id}/review", json={"verdict": "false_positive"}
    )
    assert again.status_code == 409

    feedback = session.query(ReviewerFeedback).all()
    assert [(f.verdict, f.notes) for f in feedback] == [
        ("confirmed", "card reported stolen")
    ]
    assert session.get(FraudAlert, uuid.UUID(alert_id)).state == "closed"
    assert client.get("/v1/alerts?state=open").json()["total"] == 0


def test_review_unknown_alert_is_404(client):
    res = client.patch(
        f"/v1/alerts/{uuid.uuid4()}/review", json={"verdict": "confirmed"}
    )
    assert res.status_code == 404


def test_alerts_paginate_with_cursor(client, monkeypatch):
    always(monkeypatch, "flagged")
    for _ in range(3):
        score(client)

    first = client.get("/v1/alerts?limit=2").json()
    assert len(first["alerts"]) == 2 and first["next_cursor"]
    rest = client.get("/v1/alerts", params={"limit": 2, "cursor": first["next_cursor"]})
    rest = rest.json()
    assert len(rest["alerts"]) == 1 and rest["next_cursor"] is None

    seen = {a["alert_id"] for a in first["alerts"] + rest["alerts"]}
    assert len(seen) == 3


def test_requests_share_one_connection_pool(client, monkeypatch):
    from db.models import get_engine

    always(monkeypatch, "approved")
    for _ in range(25):
        assert client.get("/v1/alerts").status_code == 200
    # The old per-request engine left one idle connection behind per call
    with get_engine().connect() as conn:
        from sqlalchemy import text

        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()"
            )
        ).scalar()
    assert count <= 6


def test_alert_list_includes_amount(client, monkeypatch):
    always(monkeypatch, "flagged")
    score(client, amount_cents=432_10, currency="EUR")
    alert = client.get("/v1/alerts").json()["alerts"][0]
    assert alert["amount_cents"] == 432_10
    assert alert["currency"] == "EUR"


def test_stats_reflect_the_whole_queue(client, session, monkeypatch):
    from db.models import FraudAlert

    assert client.get("/v1/alerts/stats").json() == {
        "open": 0,
        "in_review": 0,
        "escalated": 0,
        "closed_today": 0,
        "reviewed": 0,
        "false_positive_rate": None,
    }

    always(monkeypatch, "flagged")
    for _ in range(4):
        score(client)
    ids = [a["alert_id"] for a in client.get("/v1/alerts").json()["alerts"]]

    # One escalated alert still open, one escalated alert that gets closed
    for alert_id in ids[:2]:
        session.get(FraudAlert, uuid.UUID(alert_id)).escalated = True
    session.commit()

    client.patch(f"/v1/alerts/{ids[1]}/review", json={"verdict": "confirmed"})
    client.patch(f"/v1/alerts/{ids[2]}/review", json={"verdict": "false_positive"})

    stats = client.get("/v1/alerts/stats").json()
    assert stats["open"] == 2
    assert stats["escalated"] == 1  # closed alerts no longer count
    assert stats["closed_today"] == 2
    assert stats["reviewed"] == 2
    assert stats["false_positive_rate"] == 0.5

    # Independent of list filters and page size
    assert client.get("/v1/alerts?state=closed&limit=1").status_code == 200
    assert client.get("/v1/alerts/stats").json() == stats


def test_stats_route_is_not_treated_as_an_alert_id(client):
    assert client.get("/v1/alerts/stats").status_code == 200
