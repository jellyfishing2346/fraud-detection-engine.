"""
Train the v2 fraud model on the features the live API computes.

See ml/synthetic.py for how the training data is generated and why.

Usage (from backend/):
    python -m ml.train_v2            # writes models/xgb_fraud_v2.* (deterministic)
    python -m ml.train_v2 --rows 50000 --out /tmp/models
"""

import argparse
import json
import os
from datetime import UTC, datetime

import joblib
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from ml.synthetic import FEATURES, generate

MODEL_VERSION = "xgb-v2.0.0"
THRESHOLD = 0.4
_DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"
)


def train(rows: int = 200_000, seed: int = 42, n_estimators: int = 300) -> dict:
    """Train on synthetic data; return the fitted model, scaler and metrics."""
    X, y = generate(rows, seed=seed)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=seed
    )

    scaler = StandardScaler().fit(X_train)
    model = XGBClassifier(
        n_estimators=n_estimators,
        max_depth=4,
        learning_rate=0.1,
        subsample=0.9,
        colsample_bytree=0.9,
        # Moderate up-weighting of the rare class: recall matters more than
        # precision for a review queue, but full re-balancing floods it.
        scale_pos_weight=float(np.sqrt((y_train == 0).sum() / (y_train == 1).sum())),
        eval_metric="aucpr",
        random_state=seed,
        n_jobs=1,
    )
    model.fit(scaler.transform(X_train), y_train)

    proba = model.predict_proba(scaler.transform(X_test))[:, 1]
    flagged = proba >= THRESHOLD
    metrics = {
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "pr_auc": round(float(average_precision_score(y_test, proba)), 4),
        "precision_at_threshold": round(float(precision_score(y_test, flagged)), 4),
        "recall_at_threshold": round(float(recall_score(y_test, flagged)), 4),
        "flag_rate": round(float(flagged.mean()), 4),
        "test_rows": int(len(y_test)),
        "test_fraud_rate": round(float(y_test.mean()), 4),
    }
    return {"model": model, "scaler": scaler, "metrics": metrics}


def save(result: dict, out_dir: str, rows: int, seed: int) -> None:
    os.makedirs(out_dir, exist_ok=True)
    joblib.dump(result["model"], os.path.join(out_dir, "xgb_fraud_v2.joblib"))
    np.save(os.path.join(out_dir, "scaler_v2_mean.npy"), result["scaler"].mean_)
    np.save(os.path.join(out_dir, "scaler_v2_scale.npy"), result["scaler"].scale_)
    with open(os.path.join(out_dir, "feature_columns_v2.txt"), "w") as f:
        f.write("\n".join(FEATURES) + "\n")
    with open(os.path.join(out_dir, "xgb_fraud_v2.json"), "w") as f:
        json.dump(
            {
                "model_version": MODEL_VERSION,
                "trained_at": datetime.now(UTC).date().isoformat(),
                "training_data": "synthetic (ml/synthetic.py)",
                "rows": rows,
                "seed": seed,
                "threshold": THRESHOLD,
                "features": FEATURES,
                "metrics": result["metrics"],
            },
            f,
            indent=2,
        )
        f.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default=_DEFAULT_OUT)
    args = parser.parse_args()

    result = train(rows=args.rows, seed=args.seed)
    save(result, args.out, rows=args.rows, seed=args.seed)
    print(f"Saved {MODEL_VERSION} to {args.out}")
    for name, value in result["metrics"].items():
        print(f"  {name}: {value}")


if __name__ == "__main__":
    main()
