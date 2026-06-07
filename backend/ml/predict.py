"""
ML inference wrapper.
Loads the XGBoost model and scaler once at startup,
then scores transactions in memory — no disk reads per request.
"""

import os
from datetime import datetime

import joblib
import numpy as np

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


def load_model():
    """Call this once during FastAPI lifespan startup."""
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


# ─── Feature builder ──────────────────────────────────────────────────────────


def build_features(amount_cents: int, occurred_at: datetime) -> dict:
    """
    Build the same features used during training.
    V1-V28 are PCA features we don't have in production yet —
    we default them to 0.0 and will replace with real features in week 4.
    """
    amount = amount_cents / 100.0  # convert cents to dollars
    amount_log = float(np.log1p(amount))
    hour_of_day = occurred_at.hour
    is_night = 1 if hour_of_day >= 23 or hour_of_day <= 5 else 0

    # Build dict with all features, defaulting PCA features to 0
    features = {col: 0.0 for col in _feature_cols}
    features["amount_log"] = amount_log
    features["hour_of_day"] = float(hour_of_day)
    features["is_night"] = float(is_night)

    return features


# ─── Scorer ───────────────────────────────────────────────────────────────────


def score_transaction(amount_cents: int, occurred_at: datetime) -> dict:
    """
    Score a single transaction. Returns score, verdict, features, and metadata.
    Target latency: < 50ms.
    """
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() first.")

    features = build_features(amount_cents, occurred_at)

    # Build feature vector in the exact column order used during training
    feature_vector = np.array([[features[col] for col in _feature_cols]])
    feature_vector_scaled = _scaler.transform(feature_vector)

    score = float(_model.predict_proba(feature_vector_scaled)[0][1])

    return {
        "score": score,
        "threshold": THRESHOLD,
        "model_version": MODEL_VERSION,
        "features": {k: round(v, 6) for k, v in features.items()},
    }
