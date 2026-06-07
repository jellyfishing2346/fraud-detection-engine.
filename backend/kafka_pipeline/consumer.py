"""
Week 6: Fraud scoring Kafka consumer.

Polls transactions.raw, scores each one via the ML model,
publishes results to transactions.scored, and writes to Postgres.
Handles idempotency via kafka_offset deduplication.

Usage:
    cd backend
    python3.12 kafka/consumer.py
"""

import json
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy.orm import Session

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

from db.models import FraudAlert, FraudScore, Transaction, get_engine  # noqa: E402
from ml.predict import load_model, score_transaction  # noqa: E402

# ─── Config ──────────────────────────────────────────────────────────────────

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC_RAW = os.getenv("KAFKA_TOPIC_RAW", "transactions.raw")
TOPIC_SCORED = os.getenv("KAFKA_TOPIC_SCORED", "transactions.scored")
CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "fraud-scorer")
THRESHOLD = float(os.getenv("FRAUD_SCORE_THRESHOLD", "0.4"))


# ─── Helpers ─────────────────────────────────────────────────────────────────


def now_utc() -> datetime:
    return datetime.now(UTC)


def map_severity(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def is_duplicate(db: Session, transaction_id: uuid.UUID, kafka_offset: int) -> bool:
    """Check if this transaction has already been scored — idempotency guard."""
    existing = (
        db.query(FraudScore).filter(FraudScore.transaction_id == transaction_id).first()
    )
    return existing is not None


def process_message(
    msg: dict, kafka_offset: int, db: Session, producer: KafkaProducer
) -> None:
    """Score one transaction and write results to DB and scored topic."""
    transaction_id = uuid.UUID(msg["transaction_id"])
    user_id = uuid.UUID(msg["user_id"])
    occurred_at = datetime.fromisoformat(msg["occurred_at"])

    # Idempotency check — skip if already processed
    if is_duplicate(db, transaction_id, kafka_offset):
        print(f"  [SKIP] {transaction_id} already scored.")
        return

    # Score the transaction
    result = score_transaction(
        user_id=str(user_id),
        transaction_id=str(transaction_id),
        amount_cents=msg["amount_cents"],
        occurred_at=occurred_at,
        lat=msg.get("lat"),
        lon=msg.get("lon"),
        update_redis=True,
    )

    score_value = result["score"]
    verdict = "flagged" if score_value >= THRESHOLD else "approved"

    # Write transaction to DB
    txn = Transaction(
        id=transaction_id,
        user_id=user_id,
        merchant_id=uuid.UUID(msg["merchant_id"]) if msg.get("merchant_id") else None,
        amount_cents=msg["amount_cents"],
        currency=msg.get("currency", "USD"),
        country_code=msg.get("country_code"),
        occurred_at=occurred_at,
        status=verdict,
        kafka_offset=kafka_offset,
    )
    db.add(txn)

    # Write fraud score
    fraud_score = FraudScore(
        transaction_id=transaction_id,
        score=round(score_value, 4),
        threshold_used=THRESHOLD,
        model_version=result["model_version"],
        feature_snapshot=result["features"],
        scored_at=now_utc(),
        latency_ms=result["latency_ms"],
    )
    db.add(fraud_score)
    db.flush()

    # Create alert if flagged
    if verdict == "flagged":
        alert = FraudAlert(
            transaction_id=transaction_id,
            fraud_score_id=fraud_score.id,
            severity=map_severity(score_value),
            state="open",
            sla_deadline=now_utc() + timedelta(hours=4),
        )
        db.add(alert)

    db.commit()

    # Publish scored event to transactions.scored topic
    scored_event = {
        "transaction_id": str(transaction_id),
        "score": score_value,
        "verdict": verdict,
        "model_version": result["model_version"],
        "threshold_used": THRESHOLD,
        "top_features": result["features"],
        "scored_at": now_utc().isoformat(),
    }
    producer.send(TOPIC_SCORED, key=str(user_id), value=scored_event)

    label = "🚨 FLAGGED" if verdict == "flagged" else "✓  approved"
    print(
        f"  [{label}] {transaction_id} score={score_value:.4f} "
        f"latency={result['latency_ms']}ms"
    )


# ─── Main consumer loop ───────────────────────────────────────────────────────


def run() -> None:
    print("Loading ML model...")
    load_model()

    engine = get_engine()

    consumer = KafkaConsumer(
        TOPIC_RAW,
        bootstrap_servers=BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP,
        auto_offset_reset="earliest",
        enable_auto_commit=False,  # manual commit after DB write
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
    )

    producer = KafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        acks="all",
    )

    print(f"Listening on '{TOPIC_RAW}' (group: {CONSUMER_GROUP})...")
    print("Press Ctrl+C to stop.\n")

    try:
        for message in consumer:
            kafka_offset = message.offset
            msg = message.value

            print(
                f"Received offset={kafka_offset} "
                f"txn={msg.get('transaction_id', '?')[:8]}..."
            )

            try:
                with Session(engine) as db:
                    process_message(msg, kafka_offset, db, producer)
                # Commit offset only after successful DB write
                consumer.commit()

            except Exception as e:
                print(f"  [ERROR] Failed to process message: {e}")
                # Don't commit — message will be reprocessed on restart

    except KeyboardInterrupt:
        print("\nShutting down consumer...")
    finally:
        consumer.close()
        producer.flush()
        producer.close()
        print("Done.")


if __name__ == "__main__":
    run()
