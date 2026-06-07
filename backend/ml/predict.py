"""
Week 4: ML inference wrapper with Redis-backed features.
Loads the XGBoost model once at startup, then scores transactions
using live velocity and geo features from Redis.
"""

import os
import time
from datetime import datetime

import joblib
import numpy as np

from ml.features import build_features, post_score_update

# ─── Config ──────────────────────────────────────────────────────────────────

MODEL_PATH = os.getenv("MODEL_PATH", "models/xgb_fraud_v1.joblib")
SCALER_PATH = os.getenv("SCALER_PATH", "models/scaler_v1.joblib")
FEATURES_PATH = os.getenv("FEATURES_PATH", "models/feature_columns.txt")
THRESHOLD = float(os.getenv("FRAUD_SCORE_THRESHOLD", "0.4"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "xgb-v1.0.0")

# Loaded once at startup
_model = None
_scaler = None
_feature_cols = None


# ─── Loader ───────────────────────────────────────────────────────────────────


def load_model() -> None:
    """Call once during FastAPI lifespan startup."""
    global _model, _scaler, _feature_cols

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. "
            "Run: python ml/train.py --data notebooks/creditcard.csv"
        )

    _model = joblib.load(MODEL_PATH)
    _scaler = joblib.load(SCALER_PATH)

    with open(FEATURES_PATH) as f:
        _feature_cols = [line.strip() for line in f.readlines()]

    print(f"Model loaded: {MODEL_VERSION} ({len(_feature_cols)} features)")


# ─── Scorer ───────────────────────────────────────────────────────────────────


def score_transaction(
    user_id: str,
    transaction_id: str,
    amount_cents: int,
    occurred_at: datetime,
    lat: float | None = None,
    lon: float | None = None,
    update_redis: bool = True,
) -> dict:
    """
    Score a single transaction using live Redis features.
    Target latency: < 50ms.

    Args:
        user_id:        UUID string of the user
        transaction_id: UUID string of this transaction
        amount_cents:   transaction amount in cents
        occurred_at:    transaction datetime
        lat/lon:        optional transaction location
        update_redis:   if True, update velocity + location after scoring
    """
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")

    start = time.perf_counter()

    # 1. Build features from Redis + transaction data
    features = build_features(
        user_id=str(user_id),
        transaction_id=str(transaction_id),
        amount_cents=amount_cents,
        occurred_at=occurred_at,
        lat=lat,
        lon=lon,
    )

    # 2. Build feature vector — fill unknown columns with 0
    # (V1-V28 PCA features not available in production)
    feature_vector = np.array([[features.get(col, 0.0) for col in _feature_cols]])
    feature_vector_scaled = _scaler.transform(feature_vector)

    # 3. Score
    score = float(_model.predict_proba(feature_vector_scaled)[0][1])

    latency_ms = int((time.perf_counter() - start) * 1000)

    # 4. Update Redis after scoring (not before — don't count this txn)
    if update_redis:
        post_score_update(
            user_id=str(user_id),
            transaction_id=str(transaction_id),
            occurred_at=occurred_at,
            lat=lat,
            lon=lon,
        )

    return {
        "score": score,
        "threshold": THRESHOLD,
        "model_version": MODEL_VERSION,
        "latency_ms": latency_ms,
        "features": {k: round(v, 6) for k, v in features.items()},
    }
