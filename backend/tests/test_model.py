"""Tests for the v2 model: training data, training, and the shipped model's behaviour."""

import contextlib
import io
import math

import numpy as np
import pytest
from ml import predict, synthetic, train_v2


@pytest.fixture(scope="module")
def model():
    with contextlib.redirect_stdout(io.StringIO()):
        predict.load_model()
    return predict


def features(amount, hour, v1=0, v24=0, dist=0.0, new=0):
    return {
        "amount_log": math.log1p(amount),
        "hour_of_day": float(hour),
        "is_night": float(hour >= 23 or hour <= 5),
        "velocity_1h": float(v1),
        "velocity_24h": float(v24),
        "geo_distance_km": float(dist),
        "is_new_location": float(new),
    }


# ─── Synthetic data ───────────────────────────────────────────────────────────


def test_generator_matches_the_api_feature_set():
    X, y = synthetic.generate(5_000, seed=1)
    assert X.shape == (5_000, len(synthetic.FEATURES))
    assert synthetic.FEATURES == [
        "amount_log",
        "hour_of_day",
        "is_night",
        "velocity_1h",
        "velocity_24h",
        "geo_distance_km",
        "is_new_location",
    ]
    assert abs(y.mean() - 0.03) < 0.001


def test_generator_is_deterministic_per_seed():
    a, ya = synthetic.generate(2_000, seed=7)
    b, yb = synthetic.generate(2_000, seed=7)
    assert np.array_equal(a, b) and np.array_equal(ya, yb)
    c, _ = synthetic.generate(2_000, seed=8)
    assert not np.array_equal(a, c)


def test_generated_features_are_consistent_like_the_api():
    X, _ = synthetic.generate(20_000, seed=3)
    col = {name: X[:, i] for i, name in enumerate(synthetic.FEATURES)}
    hour = col["hour_of_day"]
    assert np.array_equal(col["is_night"] == 1, (hour >= 23) | (hour <= 5))
    assert (col["velocity_24h"] >= col["velocity_1h"]).all()
    # A new location never has a distance (mirrors get_geo_features)
    assert (col["geo_distance_km"][col["is_new_location"] == 1] == 0).all()
    # Some rows have no velocity data, as when Redis is unavailable
    assert ((col["velocity_1h"] == 0) & (col["velocity_24h"] == 0)).mean() > 0.2


# ─── Training ─────────────────────────────────────────────────────────────────


def test_training_learns_the_patterns(tmp_path):
    result = train_v2.train(rows=20_000, seed=5, n_estimators=60)
    m = result["metrics"]
    assert m["roc_auc"] > 0.85
    assert m["recall_at_threshold"] > 0.5
    # Classes overlap by design, so a perfect score would mean leakage
    assert m["pr_auc"] < 0.99

    train_v2.save(result, str(tmp_path), rows=20_000, seed=5)
    saved = {p.name for p in tmp_path.iterdir()}
    assert saved == {
        "xgb_fraud_v2.joblib",
        "scaler_v2_mean.npy",
        "scaler_v2_scale.npy",
        "feature_columns_v2.txt",
        "xgb_fraud_v2.json",
    }


# ─── Shipped model ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case",
    [
        features(4.50, 9, v24=2, dist=1.2),  # coffee
        features(85, 18, v24=1, dist=3.0),  # groceries
        features(120, 20, v24=2, dist=2_000),  # dinner while travelling
        features(1_400, 14, v24=1, dist=2.0),  # laptop at the usual place
        features(45, 13),  # no Redis data, small daytime purchase
        features(60, 19, new=1),  # first purchase from a location
    ],
)
def test_ordinary_spending_is_approved(model, case):
    assert model.score_features(case) < model.THRESHOLD


@pytest.mark.parametrize(
    "case",
    [
        features(1, 14, v1=12, v24=15, dist=0.5),  # card testing
        features(2_500, 3, dist=9_000),  # takeover from far away at night
        features(1_800, 2, new=1),  # takeover from a new location at night
        features(1_500, 16, dist=7_000),  # takeover from far away by day
        features(450, 15, v1=2, v24=22, dist=1.0),  # bust-out
        features(3_000, 3),  # no Redis data, large purchase at 3am
    ],
)
def test_fraud_patterns_are_flagged(model, case):
    assert model.score_features(case) >= model.THRESHOLD


def test_shipped_model_matches_api_features(model):
    assert model._feature_cols == synthetic.FEATURES
    assert model.MODEL_VERSION == "xgb-v2.0.0"


def test_mismatched_artifacts_fail_at_startup(monkeypatch, tmp_path):
    bad = tmp_path / "features.txt"
    bad.write_text("amount_log\nhour_of_day\n")
    monkeypatch.setattr(predict, "FEATURES_PATH", str(bad))
    with pytest.raises(ValueError, match="disagree"):
        predict.load_model()
    monkeypatch.undo()
    with contextlib.redirect_stdout(io.StringIO()):
        predict.load_model()
