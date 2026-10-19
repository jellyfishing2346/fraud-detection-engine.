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
from sklearn.preprocessing import StandardScaler

from ml.features import build_features, post_score_update

# ─── Config ──────────────────────────────────────────────────────────────────

_MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
)
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(_MODELS_DIR, "xgb_fraud_v2.joblib"))
SCALER_MEAN_PATH = os.getenv(
    "SCALER_MEAN_PATH", os.path.join(_MODELS_DIR, "scaler_v2_mean.npy")
)
SCALER_SCALE_PATH = os.getenv(
    "SCALER_SCALE_PATH", os.path.join(_MODELS_DIR, "scaler_v2_scale.npy")
)
FEATURES_PATH = os.getenv(
    "FEATURES_PATH", os.path.join(_MODELS_DIR, "feature_columns_v2.txt")
)
THRESHOLD = float(os.getenv("FRAUD_SCORE_THRESHOLD", "0.4"))
MODEL_VERSION = os.getenv("MODEL_VERSION", "xgb-v2.0.0")

_model = None
_scaler = None
_feature_cols = None


def load_model() -> None:
    """Call once during FastAPI lifespan startup."""
    global _model, _scaler, _feature_cols

    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"Model not found at {MODEL_PATH}. " "Run: python -m ml.train_v2"
        )

    _model = joblib.load(MODEL_PATH)

    # Load scaler from numpy arrays — avoids pickle version incompatibility
    _scaler = StandardScaler()
    _scaler.mean_ = np.load(SCALER_MEAN_PATH)
    _scaler.scale_ = np.load(SCALER_SCALE_PATH)
    _scaler.var_ = _scaler.scale_**2
    _scaler.n_features_in_ = len(_scaler.mean_)

    with open(FEATURES_PATH, encoding="utf-8") as f:
        _feature_cols = [line.strip() for line in f.readlines() if line.strip()]

    # Mismatched artifacts (e.g. a v1 model with the v2 feature list) would
    # otherwise only fail on the first request.
    expected = len(_feature_cols)
    if _scaler.n_features_in_ != expected or _model.n_features_in_ != expected:
        raise ValueError(
            f"Model artifacts disagree: {expected} feature columns, scaler expects "
            f"{_scaler.n_features_in_}, model expects {_model.n_features_in_}. "
            "Check MODEL_PATH, SCALER_*_PATH and FEATURES_PATH point to one version."
        )

    print(f"Model loaded: {MODEL_VERSION} ({len(_feature_cols)} features)")


def score_features(features: dict) -> float:
    """Fraud probability for an already-built feature dict."""
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")
    feature_vector = np.array([[features.get(col, 0.0) for col in _feature_cols]])
    return float(_model.predict_proba(_scaler.transform(feature_vector))[0][1])


def score_transaction(
    user_id: str,
    transaction_id: str,
    amount_cents: int,
    occurred_at: datetime,
    lat: float | None = None,
    lon: float | None = None,
    update_redis: bool = True,
) -> dict:
    """Score a single transaction using live Redis features."""
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")

    start = time.perf_counter()

    features = build_features(
        user_id=str(user_id),
        transaction_id=str(transaction_id),
        amount_cents=amount_cents,
        occurred_at=occurred_at,
        lat=lat,
        lon=lon,
    )

    score = score_features(features)
    latency_ms = int((time.perf_counter() - start) * 1000)

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
