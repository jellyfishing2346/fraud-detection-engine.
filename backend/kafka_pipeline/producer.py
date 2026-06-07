"""
Week 6: Payment gateway stub producer.

Reads transactions from the database and publishes them to the
transactions.raw Kafka topic to simulate a payment gateway.

Usage:
    cd backend
    python3.12 kafka/producer.py --count 20
"""

import argparse
import json
import os
import random
import sys
import uuid
from datetime import UTC, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from kafka import KafkaProducer

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

TOPIC = os.getenv("KAFKA_TOPIC_RAW", "transactions.raw")
BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

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
    """Publish transactions to Kafka."""
    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        acks="all",  # wait for all replicas
        retries=3,
    )

    # Use a few fixed user IDs so velocity features kick in
    users = [uuid.uuid4() for _ in range(3)]
    sent = 0

    print(f"Publishing {count} transactions to '{TOPIC}'...")

    for i in range(count):
        user_id = random.choice(users)
        high_risk = random.random() < high_risk_pct
        txn = make_transaction(user_id, high_risk=high_risk)

        producer.send(
            TOPIC,
            key=str(user_id),  # partition by user_id
            value=txn,
        )
        sent += 1
        risk_label = "HIGH RISK" if high_risk else "normal"
        print(
            f"  [{i+1}/{count}] {txn['transaction_id'][:8]}... "
            f"${txn['amount_cents']/100:.2f} {risk_label}"
        )

    producer.flush()
    producer.close()
    print(f"\nDone. Sent {sent} transactions to Kafka.")


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
