"""
Seed the database with demo data scored by the real model.

Simulates 30 days of card activity for a set of users, with a few fraud
episodes mixed in (card testing, account takeover, bust-out). Every
transaction goes through the same feature code and model as POST /v1/score,
with an in-memory stand-in for Redis so velocity and location history work
without a Redis server. Alerts exist only where the model flags a
transaction; older alerts are closed with a reviewer verdict.

Usage (from backend/):
    python scripts/seed.py              # add demo data
    python scripts/seed.py --reset      # delete ALL transactions, scores,
                                        # alerts and reviews first
"""

import argparse
import contextlib
import io
import math
import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

from api.routes.score import map_severity  # noqa: E402
from db.models import (  # noqa: E402
    FraudAlert,
    FraudScore,
    ReviewerFeedback,
    Transaction,
    create_tables,
    get_engine,
)
from ml import features, predict  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

CITIES = {
    "New York": (40.7128, -74.0060, "US"),
    "Los Angeles": (34.0522, -118.2437, "US"),
    "Chicago": (41.8781, -87.6298, "US"),
    "Toronto": (43.6532, -79.3832, "CA"),
    "London": (51.5074, -0.1278, "GB"),
    "Berlin": (52.5200, 13.4050, "DE"),
}
FAR_AWAY = [
    (55.7558, 37.6173, "RU"),
    (6.5244, 3.3792, "NG"),
    (1.3521, 103.8198, "SG"),
    (-23.5505, -46.6333, "BR"),
]
DAYS = 30
REVIEWER = uuid.UUID("00000000-0000-4000-8000-000000000001")


class InMemoryRedis:
    """The few Redis commands ml/features.py uses, kept in memory."""

    def __init__(self):
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.values: dict[str, str] = {}

    def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)

    def zcount(self, key, low, high):
        return sum(low <= s <= high for s in self.sorted_sets.get(key, {}).values())

    def expire(self, key, seconds):
        pass

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value


def _near(lat, lon, km):
    return lat + random.uniform(-km, km) / 111, lon + random.uniform(-km, km) / 111


def simulate(users: int, now: datetime) -> list[dict]:
    """Chronological list of transactions; `fraud` marks injected episodes."""
    txns = []
    start = now - timedelta(days=DAYS)
    for _ in range(users):
        user = uuid.uuid4()
        lat, lon, country = random.choice(list(CITIES.values()))
        for day in range(DAYS):
            for _ in range(random.randint(0, 4)):
                hour = random.choices(range(24), weights=[1] * 6 + [6] * 16 + [2] * 2)[
                    0
                ]
                big = random.random() < 0.05
                amount = (
                    random.lognormvariate(math.log(600), 0.6)
                    if big
                    else random.lognormvariate(math.log(35), 0.9)
                )
                at = start + timedelta(
                    days=day, hours=hour, minutes=random.randint(0, 59)
                )
                txns.append(_txn(user, amount, at, *_near(lat, lon, 5), country, False))

        roll = random.random()
        # Episodes cluster in recent days, so the review queue has a backlog
        days_ago = min(int(random.expovariate(1 / 4)), DAYS - 1)
        day = start + timedelta(days=DAYS - 1 - days_ago)
        if roll < 0.10:  # card testing burst
            at = day + timedelta(hours=random.randint(0, 23))
            for i in range(random.randint(6, 15)):
                txns.append(
                    _txn(
                        user,
                        random.uniform(0.5, 4),
                        at + timedelta(minutes=3 * i),
                        *_near(lat, lon, 5),
                        country,
                        True,
                    )
                )
        elif roll < 0.22:  # account takeover
            flat, flon, fcountry = random.choice(FAR_AWAY)
            at = day + timedelta(hours=random.choice([1, 2, 3, 4, 23]))
            for i in range(random.randint(1, 3)):
                txns.append(
                    _txn(
                        user,
                        random.lognormvariate(math.log(1200), 0.5),
                        at + timedelta(minutes=20 * i),
                        *_near(flat, flon, 10),
                        fcountry,
                        True,
                    )
                )
        elif roll < 0.27:  # bust-out
            for i in range(random.randint(18, 28)):
                txns.append(
                    _txn(
                        user,
                        random.lognormvariate(math.log(350), 0.5),
                        day + timedelta(hours=8, minutes=30 * i),
                        *_near(lat, lon, 5),
                        country,
                        True,
                    )
                )
    txns = [t for t in txns if t["occurred_at"] <= now]
    txns.sort(key=lambda t: t["occurred_at"])
    return txns


def _txn(user, amount, at, lat, lon, country, fraud):
    return {
        "user_id": user,
        "amount_cents": max(50, int(amount * 100)),
        "occurred_at": at,
        "lat": lat,
        "lon": lon,
        "country_code": country,
        "fraud": fraud,
    }


def reset(db: Session) -> None:
    for table in (ReviewerFeedback, FraudAlert, FraudScore, Transaction):
        db.query(table).delete()
    db.commit()


def seed(users: int = 60, do_reset: bool = False, seed_value: int = 42) -> dict:
    random.seed(seed_value)
    now = datetime.now(UTC)
    previous_redis = features._redis_client
    features._redis_client = InMemoryRedis()  # same feature code as the API
    try:
        return _seed(users, do_reset, now)
    finally:
        features._redis_client = previous_redis


def _seed(users: int, do_reset: bool, now: datetime) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        predict.load_model()
        create_tables()

    counts = {"transactions": 0, "alerts": 0, "open": 0, "closed": 0, "missed_fraud": 0}
    with Session(get_engine()) as db:
        if do_reset:
            reset(db)
        for t in simulate(users, now):
            txn_id = uuid.uuid4()
            result = predict.score_transaction(
                user_id=str(t["user_id"]),
                transaction_id=str(txn_id),
                amount_cents=t["amount_cents"],
                occurred_at=t["occurred_at"],
                lat=t["lat"],
                lon=t["lon"],
            )
            flagged = result["score"] >= result["threshold"]
            db.add(
                Transaction(
                    id=txn_id,
                    user_id=t["user_id"],
                    amount_cents=t["amount_cents"],
                    currency="USD",
                    country_code=t["country_code"],
                    occurred_at=t["occurred_at"],
                    status="flagged" if flagged else "approved",
                )
            )
            fraud_score = FraudScore(
                transaction_id=txn_id,
                score=result["score"],
                threshold_used=result["threshold"],
                model_version=result["model_version"],
                feature_snapshot=result["features"],
                latency_ms=result["latency_ms"],
                scored_at=t["occurred_at"],
            )
            db.add(fraud_score)
            db.flush()
            counts["transactions"] += 1
            if t["fraud"] and not flagged:
                counts["missed_fraud"] += 1
            if flagged:
                _add_alert(db, t, txn_id, fraud_score, now, counts)
        db.commit()
    return counts


def _add_alert(db, t, txn_id, fraud_score, now, counts):
    at = t["occurred_at"]
    age = now - at
    # Alerts from the last five days are still in the queue (some of today's
    # already worked); older ones have been closed with a verdict.
    closed = age > timedelta(days=5) or (
        age < timedelta(hours=12) and random.random() < 0.3
    )
    alert = FraudAlert(
        transaction_id=txn_id,
        fraud_score_id=fraud_score.id,
        severity=map_severity(float(fraud_score.score)),
        state="closed" if closed else "open",
        created_at=at,
        sla_deadline=at + timedelta(hours=4),
        escalated=not closed
        and float(fraud_score.score) >= 0.8
        and random.random() < 0.3,
    )
    db.add(alert)
    db.flush()
    counts["alerts"] += 1
    counts["closed" if closed else "open"] += 1
    if closed:
        reviewed_at = min(now, at + timedelta(minutes=random.randint(10, 300)))
        db.add(
            ReviewerFeedback(
                alert_id=alert.id,
                reviewer_id=REVIEWER,
                verdict="confirmed" if t["fraud"] else "false_positive",
                reviewed_at=reviewed_at,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed demo data scored by the real model."
    )
    parser.add_argument("--users", type=int, default=60)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="delete ALL transactions, scores, alerts and reviews before seeding",
    )
    args = parser.parse_args()
    counts = seed(users=args.users, do_reset=args.reset)
    print(f"Transactions scored: {counts['transactions']}")
    print(
        f"Flagged by the model: {counts['alerts']} "
        f"({counts['open']} open, {counts['closed']} closed with a review)"
    )
    print(f"Injected fraud the model missed: {counts['missed_fraud']}")


if __name__ == "__main__":
    main()
