import os
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Session, declarative_base, relationship

load_dotenv()

Base = declarative_base()


def now_utc():
    return datetime.now(UTC)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    merchant_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    amount_cents = Column(BigInteger, nullable=False)
    currency = Column(String(3), nullable=False)
    country_code = Column(String(2), nullable=True)
    ip_address = Column(INET, nullable=True)
    device_fingerprint = Column(Text, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")
    kafka_offset = Column(BigInteger, nullable=True, unique=True)

    scores = relationship("FraudScore", back_populates="transaction")


class FraudScore(Base):
    __tablename__ = "fraud_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False
    )
    score = Column(Numeric(5, 4), nullable=False)
    threshold_used = Column(Numeric(5, 4), nullable=False)
    model_version = Column(String(50), nullable=False)
    feature_snapshot = Column(JSONB, nullable=True)
    scored_at = Column(DateTime(timezone=True), default=now_utc)
    latency_ms = Column(Integer, nullable=True)

    transaction = relationship("Transaction", back_populates="scores")
    alerts = relationship("FraudAlert", back_populates="fraud_score")


class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), nullable=False
    )
    fraud_score_id = Column(
        UUID(as_uuid=True), ForeignKey("fraud_scores.id"), nullable=False
    )
    severity = Column(String(10), nullable=False)
    state = Column(String(20), nullable=False, default="open")
    assigned_to = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=now_utc, index=True)
    sla_deadline = Column(DateTime(timezone=True), nullable=False)
    escalated = Column(Boolean, default=False)

    fraud_score = relationship("FraudScore", back_populates="alerts")
    feedback = relationship("ReviewerFeedback", back_populates="alert")


class ReviewerFeedback(Base):
    __tablename__ = "reviewer_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    alert_id = Column(UUID(as_uuid=True), ForeignKey("fraud_alerts.id"), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), nullable=False)
    verdict = Column(String(20), nullable=False)
    notes = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), default=now_utc)
    used_in_training = Column(Boolean, default=False)

    alert = relationship("FraudAlert", back_populates="feedback")


def get_engine():
    return create_engine(os.getenv("DATABASE_URL"))


def get_session():
    engine = get_engine()
    with Session(engine) as session:
        yield session


def create_tables():
    engine = get_engine()
    Base.metadata.create_all(engine)
    print("Tables ready.")


if __name__ == "__main__":
    create_tables()
