import uuid
from datetime import UTC, datetime

from db.models import FraudAlert, FraudScore, ReviewerFeedback, Transaction, get_session
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter()


# ─── Response schemas ─────────────────────────────────────────────────────────


class AlertSummary(BaseModel):
    alert_id: uuid.UUID
    transaction_id: uuid.UUID
    score: float
    severity: str
    state: str
    sla_deadline: datetime
    escalated: bool
    created_at: datetime


class AlertDetail(BaseModel):
    alert_id: uuid.UUID
    transaction_id: uuid.UUID
    score: float
    severity: str
    state: str
    sla_deadline: datetime
    escalated: bool
    created_at: datetime
    amount_cents: int
    currency: str
    country_code: str | None
    top_features: dict | None


class AlertListResponse(BaseModel):
    alerts: list[AlertSummary]
    total: int
    next_cursor: str | None


class ReviewRequest(BaseModel):
    verdict: str  # "confirmed" | "false_positive"
    notes: str | None = None


class ReviewResponse(BaseModel):
    alert_id: uuid.UUID
    state: str
    verdict: str
    reviewed_at: datetime


# ─── GET /alerts ──────────────────────────────────────────────────────────────


@router.get("/alerts", response_model=AlertListResponse)
def list_alerts(
    state: str | None = Query(None, description="open | in_review | closed"),
    severity: str | None = Query(None, description="low | medium | high"),
    limit: int = Query(20, le=100),
    cursor: str | None = Query(None, description="created_at cursor for pagination"),
    db: Session = Depends(get_session),
):
    query = db.query(FraudAlert)

    if state:
        query = query.filter(FraudAlert.state == state)
    if severity:
        query = query.filter(FraudAlert.severity == severity)
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.filter(FraudAlert.created_at < cursor_dt)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid cursor format."
            ) from None

    total = query.count()
    alerts = query.order_by(FraudAlert.created_at.desc()).limit(limit).all()

    next_cursor = None
    if len(alerts) == limit:
        next_cursor = alerts[-1].created_at.isoformat()

    return AlertListResponse(
        alerts=[
            AlertSummary(
                alert_id=a.id,
                transaction_id=a.transaction_id,
                score=float(a.fraud_score.score) if a.fraud_score else 0.0,
                severity=a.severity,
                state=a.state,
                sla_deadline=a.sla_deadline,
                escalated=a.escalated,
                created_at=a.created_at,
            )
            for a in alerts
        ],
        total=total,
        next_cursor=next_cursor,
    )


# ─── GET /alerts/{alert_id} ───────────────────────────────────────────────────


@router.get("/alerts/{alert_id}", response_model=AlertDetail)
def get_alert(alert_id: uuid.UUID, db: Session = Depends(get_session)):
    alert = db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")

    txn = db.query(Transaction).filter(Transaction.id == alert.transaction_id).first()
    fraud_score = (
        db.query(FraudScore).filter(FraudScore.id == alert.fraud_score_id).first()
    )

    top_features = None
    if fraud_score and fraud_score.feature_snapshot:
        # Return top 5 features by absolute value for the reviewer
        features = fraud_score.feature_snapshot
        top_features = dict(
            sorted(features.items(), key=lambda x: abs(float(x[1])), reverse=True)[:5]
        )

    return AlertDetail(
        alert_id=alert.id,
        transaction_id=alert.transaction_id,
        score=float(fraud_score.score) if fraud_score else 0.0,
        severity=alert.severity,
        state=alert.state,
        sla_deadline=alert.sla_deadline,
        escalated=alert.escalated,
        created_at=alert.created_at,
        amount_cents=txn.amount_cents if txn else 0,
        currency=txn.currency if txn else "USD",
        country_code=txn.country_code if txn else None,
        top_features=top_features,
    )


# ─── PATCH /alerts/{alert_id}/review ─────────────────────────────────────────


@router.patch("/alerts/{alert_id}/review", response_model=ReviewResponse)
def review_alert(
    alert_id: uuid.UUID,
    body: ReviewRequest,
    db: Session = Depends(get_session),
):
    alert = db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found.")
    if alert.state == "closed":
        raise HTTPException(status_code=409, detail="Alert already closed.")

    if body.verdict not in ("confirmed", "false_positive"):
        raise HTTPException(
            status_code=422,
            detail="verdict must be 'confirmed' or 'false_positive'.",
        )

    # Record reviewer feedback
    reviewed_at = datetime.now(UTC)
    feedback = ReviewerFeedback(
        alert_id=alert_id,
        reviewer_id=uuid.uuid4(),  # TODO week 5: replace with auth user id
        verdict=body.verdict,
        notes=body.notes,
        reviewed_at=reviewed_at,
    )
    db.add(feedback)

    # Close the alert
    alert.state = "closed"
    db.commit()

    return ReviewResponse(
        alert_id=alert_id,
        state="closed",
        verdict=body.verdict,
        reviewed_at=reviewed_at,
    )
