"""
Redis Streams consumer (replaces Kafka).

Polls transactions.raw stream, scores each one via the ML model,
publishes results to transactions.scored stream, and writes to Postgres.
Handles idempotency via Redis Stream message ID deduplication.

Usage:
    cd backend
    python3.12 redis_pipeline/consumer.py
"""

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import redis
from dotenv import load_dotenv
from sqlalchemy.orm import Session

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

from db.models import FraudAlert, FraudScore, Transaction, get_engine  # noqa: E402
from ml.predict import load_model, score_transaction  # noqa: E402

# ─── Config ──────────────────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_RAW = os.getenv("REDIS_STREAM_RAW", "transactions.raw")
STREAM_SCORED = os.getenv("REDIS_STREAM_SCORED", "transactions.scored")
CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "fraud-scorer")
CONSUMER_NAME = os.getenv("REDIS_CONSUMER_NAME", "fraud-scorer-1")
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


def is_duplicate(db: Session, transaction_id: uuid.UUID) -> bool:
    """Check if this transaction has already been scored — idempotency guard."""
    existing = (
        db.query(FraudScore).filter(FraudScore.transaction_id == transaction_id).first()
    )
    return existing is not None


def process_message(msg: dict, message_id: str, db: Session, r: redis.Redis) -> None:
    """Score one transaction and write results to DB and scored stream."""
    transaction_id = uuid.UUID(msg[b"transaction_id"].decode("utf-8"))
    user_id = uuid.UUID(msg[b"user_id"].decode("utf-8"))
    occurred_at = datetime.fromisoformat(msg[b"occurred_at"].decode("utf-8"))

    # Idempotency check — skip if already processed
    if is_duplicate(db, transaction_id):
        print(f"  [SKIP] {transaction_id} already scored.")
        return

    # Score the transaction
    result = score_transaction(
        user_id=str(user_id),
        transaction_id=str(transaction_id),
        amount_cents=int(msg[b"amount_cents"].decode("utf-8")),
        occurred_at=occurred_at,
        lat=float(msg[b"lat"].decode("utf-8")),
        lon=float(msg[b"lon"].decode("utf-8")),
        update_redis=True,
    )

    score_value = result["score"]
    verdict = "flagged" if score_value >= THRESHOLD else "approved"

    # Write transaction to DB
    txn = Transaction(
        id=transaction_id,
        user_id=user_id,
        merchant_id=uuid.UUID(msg[b"merchant_id"].decode("utf-8"))
        if msg.get(b"merchant_id")
        else None,
        amount_cents=int(msg[b"amount_cents"].decode("utf-8")),
        currency=msg.get(b"currency", b"USD").decode("utf-8"),
        country_code=msg.get(b"country_code").decode("utf-8")
        if msg.get(b"country_code")
        else None,
        occurred_at=occurred_at,
        status=verdict,
        kafka_offset=None,  # Redis Streams use message IDs instead
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

    # Publish scored event to transactions.scored stream
    scored_event = {
        "transaction_id": str(transaction_id),
        "score": score_value,
        "verdict": verdict,
        "model_version": result["model_version"],
        "threshold_used": THRESHOLD,
        "top_features": result["features"],
        "scored_at": now_utc().isoformat(),
    }

    # Convert dict to bytes for Redis
    event_data = {k: str(v) for k, v in scored_event.items()}
    r.xadd(STREAM_SCORED, event_data)

    label = "🚨 FLAGGED" if verdict == "flagged" else "✓  approved"
    print(
        f"  [{label}] {transaction_id} score={score_value:.4f} "
        f"latency={result['latency_ms']}ms"
    )


# ─── Main consumer loop ───────────────────────────────────────────────────────


def run() -> None:
    print("Loading ML model...")
    load_model()

    # Parse Redis URL
    if REDIS_URL.startswith("rediss://"):
        r = redis.from_url(REDIS_URL, ssl_cert_reqs=None)
    else:
        r = redis.from_url(REDIS_URL)

    engine = get_engine()

    # Create consumer group if it doesn't exist
    try:
        r.xgroup_create(STREAM_RAW, CONSUMER_GROUP, id="0", mkstream=True)
        print(f"Created consumer group '{CONSUMER_GROUP}'")
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            print(f"Error creating consumer group: {e}")
        else:
            print(f"Consumer group '{CONSUMER_GROUP}' already exists")

    print(f"Listening on Redis stream '{STREAM_RAW}' (group: {CONSUMER_GROUP})...")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            # Read new messages with blocking
            messages = r.xreadgroup(
                CONSUMER_GROUP,
                CONSUMER_NAME,
                {STREAM_RAW: ">"},
                count=1,
                block=5000,  # 5 second timeout
            )

            if not messages:
                continue

            for _, stream_messages in messages:
                for message_id, msg in stream_messages:
                    print(
                        f"Received message_id={message_id.decode('utf-8')} "
                        f"txn={msg.get(b'transaction_id', b'?').decode('utf-8')[:8]}..."
                    )

                    try:
                        with Session(engine) as db:
                            process_message(msg, message_id.decode("utf-8"), db, r)
                        # Acknowledge message processing
                        r.xack(STREAM_RAW, CONSUMER_GROUP, message_id)

                    except Exception as e:
                        print(f"  [ERROR] Failed to process message: {e}")
                        # Don't ack — message will be reprocessed

    except KeyboardInterrupt:
        print("\nShutting down consumer...")
    finally:
        print("Done.")


if __name__ == "__main__":
    run()
