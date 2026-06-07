"""
Week 8: Seed script — loads 1000 realistic test transactions.

Generates a mix of legitimate and suspicious transactions across
multiple users so the dashboard has meaningful data on first run.

Usage:
    cd backend
    python3.12 scripts/seed.py
"""

import os
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

from db.models import FraudAlert, FraudScore, Transaction, get_engine  # noqa: E402

# ─── Config ──────────────────────────────────────────────────────────────────

TOTAL_TRANSACTIONS = 1000
FRAUD_RATE = 0.08  # 8% fraud rate — realistic for card fraud
SEED = 42
random.seed(SEED)

MERCHANTS = [uuid.uuid4() for _ in range(20)]
USERS = [uuid.uuid4() for _ in range(50)]

LOCATIONS = [
    (40.7128, -74.0060, "US"),  # New York
    (34.0522, -118.2437, "US"),  # Los Angeles
    (41.8781, -87.6298, "US"),  # Chicago
    (51.5074, -0.1278, "GB"),  # London
    (48.8566, 2.3522, "FR"),  # Paris
    (35.6762, 139.6503, "JP"),  # Tokyo
    (52.5200, 13.4050, "DE"),  # Berlin
    (55.7558, 37.6173, "RU"),  # Moscow
    (-33.8688, 151.2093, "AU"),  # Sydney
    (1.3521, 103.8198, "SG"),  # Singapore
]

MERCHANT_CATEGORIES = [
    "grocery",
    "restaurant",
    "gas_station",
    "pharmacy",
    "electronics",
    "clothing",
    "hotel",
    "airline",
    "crypto_exchange",
    "wire_transfer",
]


# ─── Transaction generators ───────────────────────────────────────────────────


def random_time(days_back: int = 30) -> datetime:
    """Random timestamp within the last N days."""
    now = datetime.now(UTC)
    offset = random.randint(0, days_back * 24 * 60 * 60)
    return now - timedelta(seconds=offset)


def legit_transaction(user_id: uuid.UUID) -> dict:
    """Generate a realistic legitimate transaction."""
    lat, lon, country = random.choice(LOCATIONS[:5])  # stay in common locations
    hour = random.randint(8, 22)  # business hours
    occurred_at = random_time().replace(hour=hour)
    amount = random.randint(5_00, 200_00)  # $5 - $200

    return {
        "user_id": user_id,
        "merchant_id": random.choice(MERCHANTS),
        "amount_cents": amount,
        "currency": "USD",
        "country_code": country,
        "occurred_at": occurred_at,
        "lat": lat + random.uniform(-0.01, 0.01),
        "lon": lon + random.uniform(-0.01, 0.01),
        "score": random.uniform(0.01, 0.15),
        "is_fraud": False,
    }


def fraud_transaction(user_id: uuid.UUID) -> dict:
    """Generate a suspicious transaction with fraud indicators."""
    lat, lon, country = random.choice(LOCATIONS[3:])  # unusual locations
    hour = random.choice([1, 2, 3, 4, 23])  # late night
    occurred_at = random_time(7).replace(hour=hour)  # recent
    amount = random.randint(200_00, 5000_00)  # $200 - $5000

    return {
        "user_id": user_id,
        "merchant_id": random.choice(MERCHANTS[-5:]),  # high-risk merchants
        "amount_cents": amount,
        "currency": "USD",
        "country_code": country,
        "occurred_at": occurred_at,
        "lat": lat + random.uniform(-0.1, 0.1),
        "lon": lon + random.uniform(-0.1, 0.1),
        "score": random.uniform(0.42, 0.97),
        "is_fraud": True,
    }


# ─── Seeder ───────────────────────────────────────────────────────────────────


def seed() -> None:
    engine = get_engine()
    fraud_count = int(TOTAL_TRANSACTIONS * FRAUD_RATE)
    legit_count = TOTAL_TRANSACTIONS - fraud_count

    print(
        f"Seeding {TOTAL_TRANSACTIONS} transactions "
        f"({legit_count} legit, {fraud_count} fraud)..."
    )

    transactions = []
    for _ in range(legit_count):
        user_id = random.choice(USERS)
        transactions.append(legit_transaction(user_id))
    for _ in range(fraud_count):
        user_id = random.choice(USERS)
        transactions.append(fraud_transaction(user_id))

    random.shuffle(transactions)

    alerts_created = 0
    written = 0

    with Session(engine) as db:
        for _, t in enumerate(transactions):
            txn_id = uuid.uuid4()
            verdict = "flagged" if t["is_fraud"] else "approved"

            txn = Transaction(
                id=txn_id,
                user_id=t["user_id"],
                merchant_id=t["merchant_id"],
                amount_cents=t["amount_cents"],
                currency=t["currency"],
                country_code=t["country_code"],
                occurred_at=t["occurred_at"],
                status=verdict,
            )
            db.add(txn)
            db.flush()

            score_val = t["score"]
            severity = (
                "high" if score_val >= 0.8 else "medium" if score_val >= 0.6 else "low"
            )

            import math

            fs = FraudScore(
                transaction_id=txn_id,
                score=round(score_val, 4),
                threshold_used=0.4,
                model_version="xgb-v1.0.0",
                feature_snapshot={
                    "amount_log": round(math.log1p(t["amount_cents"] / 100), 4),
                    "hour_of_day": float(t["occurred_at"].hour),
                    "is_night": float(
                        t["occurred_at"].hour <= 5 or t["occurred_at"].hour >= 23
                    ),
                    "velocity_1h": float(random.randint(0, 5) if t["is_fraud"] else 0),
                    "geo_distance_km": round(
                        random.uniform(5000, 12000)
                        if t["is_fraud"]
                        else random.uniform(0, 50),
                        2,
                    ),
                },
                latency_ms=random.randint(1, 30),
            )
            db.add(fs)
            db.flush()

            if t["is_fraud"]:
                sla_offset = timedelta(hours=random.uniform(0.5, 4))
                alert = FraudAlert(
                    transaction_id=txn_id,
                    fraud_score_id=fs.id,
                    severity=severity,
                    state=random.choice(["open", "open", "open", "closed"]),
                    sla_deadline=t["occurred_at"] + sla_offset,
                    escalated=random.random() < 0.1,
                )
                db.add(alert)
                alerts_created += 1

            written += 1
            if written % 100 == 0:
                db.commit()
                print(f"  {written}/{TOTAL_TRANSACTIONS} written...")

        db.commit()

    print("\nDone.")
    print(f"  Transactions: {TOTAL_TRANSACTIONS}")
    print(f"  Fraud alerts: {alerts_created}")
    print(f"  Open alerts:  {int(alerts_created * 0.75)}")
    print("\nOpen http://localhost:8000/dashboard to see the data.")


if __name__ == "__main__":
    seed()
