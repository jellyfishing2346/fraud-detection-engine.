"""
Redis Streams producer (replaces Kafka).

Reads transactions from the database and publishes them to Redis Streams
to simulate a payment gateway.

Usage:
    cd backend
    python3.12 redis_pipeline/producer.py --count 20
"""

import argparse
import os
import random
import sys
import uuid
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

STREAM_NAME = os.getenv("REDIS_STREAM_RAW", "transactions.raw")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Sample merchants and locations for realistic test data
MERCHANTS = [
    uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001"),
    uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002"),
    uuid.UUID("aaaaaaaa-0000-0000-0000-000000000003"),
]

LOCATIONS = [
    (40.7128, -74.0060),  # New York
    (34.0522, -118.2437),  # Los Angeles
    (51.5074, -0.1278),  # London
    (48.8566, 2.3522),  # Paris
    (35.6762, 139.6503),  # Tokyo
]


def make_transaction(user_id: uuid.UUID, high_risk: bool = False) -> dict:
    """Generate a realistic transaction payload."""
    now = datetime.now(UTC)

    if high_risk:
        # High risk: large amount, night time, random location
        amount_cents = random.randint(500_00, 10_000_00)
        occurred_at = now.replace(hour=random.choice([1, 2, 3, 4]))
        lat, lon = random.choice(LOCATIONS)
    else:
        # Normal: moderate amount, business hours
        amount_cents = random.randint(10_00, 500_00)
        occurred_at = now.replace(hour=random.randint(9, 18))
        lat, lon = random.choice(LOCATIONS)

    return {
        "transaction_id": str(uuid.uuid4()),
        "user_id": str(user_id),
        "merchant_id": str(random.choice(MERCHANTS)),
        "amount_cents": amount_cents,
        "currency": "USD",
        "country_code": "US",
        "occurred_at": occurred_at.isoformat(),
        "lat": lat,
        "lon": lon,
    }


def produce(count: int = 10, high_risk_pct: float = 0.2) -> None:
    """Publish transactions to Redis Streams."""
    # Parse Redis URL to get host and port
    if REDIS_URL.startswith("rediss://"):
        # Upstash uses rediss://
        r = redis.from_url(REDIS_URL, ssl_cert_reqs=None)
    else:
        r = redis.from_url(REDIS_URL)

    # Use a few fixed user IDs so velocity features kick in
    users = [uuid.uuid4() for _ in range(3)]
    sent = 0

    print(f"Publishing {count} transactions to Redis stream '{STREAM_NAME}'...")

    for i in range(count):
        user_id = random.choice(users)
        high_risk = random.random() < high_risk_pct
        txn = make_transaction(user_id, high_risk=high_risk)

        # Add to Redis Stream
        r.xadd(
            STREAM_NAME,
            {
                "transaction_id": txn["transaction_id"],
                "user_id": str(user_id),
                "merchant_id": txn["merchant_id"],
                "amount_cents": str(txn["amount_cents"]),
                "currency": txn["currency"],
                "country_code": txn["country_code"],
                "occurred_at": txn["occurred_at"],
                "lat": str(txn["lat"]),
                "lon": str(txn["lon"]),
            },
        )

        sent += 1
        risk_label = "HIGH RISK" if high_risk else "normal"
        print(
            f"  [{i+1}/{count}] {txn['transaction_id'][:8]}... "
            f"${txn['amount_cents']/100:.2f} {risk_label}"
        )

    print(f"\nDone. Sent {sent} transactions to Redis Stream.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10, help="Number of transactions")
    parser.add_argument(
        "--high-risk-pct",
        type=float,
        default=0.2,
        help="Fraction of high-risk transactions (0-1)",
    )
    args = parser.parse_args()
    produce(count=args.count, high_risk_pct=args.high_risk_pct)
