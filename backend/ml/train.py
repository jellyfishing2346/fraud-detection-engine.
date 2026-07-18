"""
Week 2: XGBoost fraud detection model training script.

Usage:
    python ml/train.py --data notebooks/creditcard.csv

Downloads:
    Dataset: https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
    Place creditcard.csv in the notebooks/ folder before running.
"""

import argparse
import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# ─── Config ──────────────────────────────────────────────────────────────────

FRAUD_THRESHOLD = 0.4  # score >= this → flagged
RANDOM_STATE = 42
TEST_SIZE = 0.2
MODEL_DIR = "models"
MODEL_NAME = "xgb_fraud_v1.joblib"
SCALER_NAME = "scaler_v1.joblib"


# ─── Feature engineering ─────────────────────────────────────────────────────


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    The Kaggle dataset already has PCA features V1–V28 plus Amount and Time.
    We add a few interpretable features on top.
    """
    df = df.copy()

    # Normalise Amount — raw dollar values have very different scales
    df["amount_log"] = np.log1p(df["Amount"])

    # Time of day: the Time column is seconds since first transaction in the dataset
    df["hour_of_day"] = (df["Time"] % 86400) // 3600

    # Flag night-time transactions (11pm – 5am) — higher fraud rate
    df["is_night"] = df["hour_of_day"].apply(lambda h: 1 if h >= 23 or h <= 5 else 0)

    # Drop the raw columns we've replaced or don't need
    df = df.drop(columns=["Time", "Amount"])

    return df


def get_feature_columns(df: pd.DataFrame) -> list:
    return [c for c in df.columns if c != "Class"]


# ─── Training ────────────────────────────────────────────────────────────────


def train(data_path: str):
    print(f"\n{'=' * 55}")
    print("  Fraud Detection Model Training")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 55}\n")

    # 1. Load data
    print("1. Loading dataset...")
    df = pd.read_csv(data_path)
    print(f"   Rows: {len(df):,}  -  Columns: {df.shape[1]}")
    fraud_pct = df["Class"].mean() * 100
    print(f"   Fraud rate: {fraud_pct:.3f}%  ({df['Class'].sum():,} fraudulent)")

    # 2. Feature engineering
    print("\n2. Engineering features...")
    df = engineer_features(df)
    feature_cols = get_feature_columns(df)
    print(f"   Features: {feature_cols}")

    X = df[feature_cols]
    y = df["Class"]

    # 3. Train / test split (stratified to preserve fraud ratio)
    print("\n3. Splitting data...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    print(f"   Train: {len(X_train):,}  -  Test: {len(X_test):,}")

    # 4. Scale features
    print("\n4. Scaling features...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 5. SMOTE oversampling — fixes the 0.17% fraud class imbalance
    print("\n5. Applying SMOTE oversampling...")
    smote = SMOTE(random_state=RANDOM_STATE)
    X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)
    print(f"   Before: {y_train.sum():,} fraud / {len(y_train):,} total")
    print(
        f"   After:  {y_train_resampled.sum():,} fraud / {len(y_train_resampled):,} total"
    )

    # 6. Train XGBoost
    print("\n6. Training XGBoost classifier...")
    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=1,  # SMOTE handles balancing, so keep this at 1
        random_state=RANDOM_STATE,
        eval_metric="logloss",
        verbosity=0,
    )
    model.fit(X_train_resampled, y_train_resampled)
    print("   Training complete.")

    # 7. Evaluate at our chosen threshold
    print(f"\n7. Evaluating at threshold = {FRAUD_THRESHOLD}...")
    y_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_pred = (y_proba >= FRAUD_THRESHOLD).astype(int)

    print("\n   Classification report:")
    print(classification_report(y_test, y_pred, target_names=["Legit", "Fraud"]))

    print("   Confusion matrix (rows=actual, cols=predicted):")
    cm = confusion_matrix(y_test, y_pred)
    print(f"   {'':10} Pred Legit  Pred Fraud")
    print(f"   {'Actual Legit':12} {cm[0][0]:>8,}  {cm[0][1]:>10,}")
    print(f"   {'Actual Fraud':12} {cm[1][0]:>8,}  {cm[1][1]:>10,}")

    roc = roc_auc_score(y_test, y_proba)
    recall = cm[1][1] / (cm[1][0] + cm[1][1])
    fpr = cm[0][1] / (cm[0][0] + cm[0][1])
    print(f"\n   ROC-AUC:      {roc:.4f}")
    print(f"   Recall:       {recall:.4f}  (fraud caught — higher is better)")
    print(f"   False pos rate: {fpr:.4f}  (legit flagged — lower is better)")

    if recall < 0.80:
        print("\n   ⚠  Recall below 0.80 — consider lowering FRAUD_THRESHOLD.")
    else:
        print("\n   ✓  Recall target met (≥ 0.80).")

    # 8. Save model and scaler
    print("\n8. Saving model...")
    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, MODEL_NAME)
    scaler_path = os.path.join(MODEL_DIR, SCALER_NAME)
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    print(f"   Model  → {model_path}")
    print(f"   Scaler → {scaler_path}")

    # 9. Save feature list so the API uses the same columns in the same order
    feature_path = os.path.join(MODEL_DIR, "feature_columns.txt")
    with open(feature_path, "w") as f:
        f.write("\n".join(feature_cols))
    print(f"   Features → {feature_path}")

    print(f"\n{'=' * 55}")
    print("  Training complete. Ready for week 3.")
    print(f"{'=' * 55}\n")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        default="notebooks/creditcard.csv",
        help="Path to creditcard.csv from Kaggle",
    )
    args = parser.parse_args()

    if not os.path.exists(args.data):
        print(f"\nError: Dataset not found at '{args.data}'")
        print("Download from: https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud")
        print("Place creditcard.csv in the notebooks/ folder.\n")
        exit(1)

    train(args.data)
