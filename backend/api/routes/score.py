import time
import uuid
from datetime import UTC, datetime

from db.models import FraudAlert, FraudScore, Transaction, get_session
from fastapi import APIRouter, Depends, HTTPException
from ml.predict import score_transaction
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()


# ─── Request / Response schemas ──────────────────────────────────────────────


class ScoreRequest(BaseModel):
    transaction_id: uuid.UUID
    user_id: uuid.UUID
    merchant_id: uuid.UUID | None = None
    amount_cents: int  # never float
    currency: str = "USD"
    country_code: str | None = None
    ip_address: str | None = None
    device_fingerprint: str | None = None
    occurred_at: datetime


class ScoreResponse(BaseModel):
    transaction_id: uuid.UUID
    score: float
    verdict: str  # "approved" | "flagged"
    severity: str | None  # None if approved
    latency_ms: int
    model_version: str


# ─── Helpers ─────────────────────────────────────────────────────────────────


def map_severity(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def now_utc() -> datetime:
    return datetime.now(UTC)


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.post("/score", response_model=ScoreResponse)
def score(request: ScoreRequest, db: Session = Depends(get_session)):
    start = time.perf_counter()

    # 1. Check for duplicate (idempotency via transaction_id)
    existing = (
        db.query(FraudScore)
        .filter(FraudScore.transaction_id == request.transaction_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Transaction already scored.")

    # 2. Run ML model
    result = score_transaction(
        amount_cents=request.amount_cents,
        occurred_at=request.occurred_at,
    )
    score_value = result["score"]
    verdict = "flagged" if score_value >= result["threshold"] else "approved"
    latency_ms = int((time.perf_counter() - start) * 1000)

    # 3. Persist transaction
    txn = Transaction(
        id=request.transaction_id,
        user_id=request.user_id,
        merchant_id=request.merchant_id,
        amount_cents=request.amount_cents,
        currency=request.currency,
        country_code=request.country_code,
        ip_address=request.ip_address,
        device_fingerprint=request.device_fingerprint,
        occurred_at=request.occurred_at,
        status=verdict,
    )
    db.add(txn)

    # 4. Persist fraud score
    fraud_score = FraudScore(
        transaction_id=request.transaction_id,
        score=round(score_value, 4),
        threshold_used=result["threshold"],
        model_version=result["model_version"],
        feature_snapshot=result["features"],
        scored_at=now_utc(),
        latency_ms=latency_ms,
    )
    db.add(fraud_score)
    db.flush()  # get fraud_score.id before committing

    # 5. Create alert if flagged
    if verdict == "flagged":
        from datetime import timedelta

        alert = FraudAlert(
            transaction_id=request.transaction_id,
            fraud_score_id=fraud_score.id,
            severity=map_severity(score_value),
            state="open",
            sla_deadline=now_utc() + timedelta(hours=4),
        )
        db.add(alert)

    db.commit()

    return ScoreResponse(
        transaction_id=request.transaction_id,
        score=score_value,
        verdict=verdict,
        severity=map_severity(score_value) if verdict == "flagged" else None,
        latency_ms=latency_ms,
        model_version=result["model_version"],
    )
