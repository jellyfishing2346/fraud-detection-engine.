# 🤖 ML Model Guide

## Dataset

**Source:** [Kaggle Credit Card Fraud Detection](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud)

| Stat | Value |
|---|---|
| Total transactions | 284,807 |
| Fraudulent | 492 (0.173%) |
| Legitimate | 284,315 (99.827%) |
| Features | 31 (V1–V28 PCA + Time + Amount + Class) |
| Time period | 2 days of European cardholder transactions |

The dataset is intentionally challenging — the extreme class imbalance (0.17% fraud) means naive models that predict "all legitimate" achieve 99.83% accuracy while catching zero fraud.

---

## Feature Engineering

### Dataset features (V1–V28)
The original dataset contains PCA-transformed features to protect cardholder privacy. These 28 components capture patterns in the raw transaction data that we don't have access to.

### Engineered features

| Feature | Type | Description | Signal |
|---|---|---|---|
| `amount_log` | float | `log1p(amount_dollars)` | Raw amounts are right-skewed; log normalises the distribution |
| `hour_of_day` | int | Hour of transaction (0–23) | Fraud peaks at 1–4am |
| `is_night` | binary | 1 if hour ≥ 23 or ≤ 5 | Flags late-night transactions |
| `velocity_1h` | int | Txns by this user in last 60 mins | Multiple rapid transactions = strong fraud signal |
| `velocity_24h` | int | Txns by this user in last 24h | Longer-window velocity |
| `geo_distance_km` | float | Haversine distance from last location | NY → London in 5 mins = impossible |
| `is_new_location` | binary | 1 if no prior location on record | First-time location |

### Why log-transform amount?
Transaction amounts follow a power law distribution — most are small ($5–$50) but the tail extends to thousands. Without transformation, large amounts dominate the model's gradient updates. `log1p` compresses the range while preserving ordinality.

### Haversine distance formula
```python
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0  # Earth radius in km
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return r * 2 * atan2(sqrt(a), sqrt(1-a))
```

---

## Class Imbalance: SMOTE

With only 0.17% fraud, a naive classifier learns to always predict "legitimate". We use **SMOTE** (Synthetic Minority Oversampling Technique) to balance the training set.

### How SMOTE works
1. For each minority class sample, find its k-nearest neighbours in feature space
2. Generate synthetic samples along the line segments connecting them
3. Result: a balanced training set without simple duplication

```
Before SMOTE:
  Legitimate: 227,451  (99.83%)
  Fraud:          394   (0.17%)

After SMOTE:
  Legitimate: 227,451  (50%)
  Fraud:      227,451  (50%)  ← synthetic samples added
```

> **Important:** SMOTE is applied only to the training set. The test set remains at the natural 0.17% fraud rate to evaluate real-world performance.

---

## Model: XGBoost

```python
XGBClassifier(
    n_estimators=200,      # 200 trees
    max_depth=6,           # moderate depth — avoids overfitting
    learning_rate=0.1,     # shrinkage per tree
    subsample=0.8,         # row sampling per tree
    colsample_bytree=0.8,  # feature sampling per tree
    scale_pos_weight=1,    # SMOTE handles balancing
    eval_metric='logloss',
)
```

### Why XGBoost over alternatives?

| Model | Pros | Cons | Verdict |
|---|---|---|---|
| **XGBoost** | Fast inference, interpretable, handles tabular well | Black box at tree level | ✅ Chosen |
| Logistic Regression | Fully interpretable | Assumes linearity, misses interactions | ❌ Too simple |
| Random Forest | Robust, interpretable | 10x slower inference | ❌ Too slow |
| Neural Network | Handles complex patterns | 100ms+ inference, opaque | ❌ Too slow + opaque |
| Isolation Forest | Unsupervised, no labels needed | Lower accuracy with labels | ❌ Labels available |

---

## Threshold Tuning

The model outputs a probability between 0 and 1. The **threshold** determines what score counts as fraud.

```
score < threshold  → APPROVED
score ≥ threshold  → FLAGGED
```

### The tradeoff

| Threshold | Recall (fraud caught) | False positive rate |
|---|---|---|
| 0.3 | 94% | 0.21% |
| **0.4** | **89%** | **0.08%** |
| 0.5 | 82% | 0.04% |
| 0.6 | 74% | 0.02% |

**We chose 0.4** — missing real fraud costs ~10–100x more than a false positive. At 0.08% FPR, only 8 in 10,000 legitimate transactions get flagged, and the reviewer dashboard handles those efficiently.

### Precision-Recall curve
The P-R curve shows the tradeoff at every possible threshold. We target recall ≥ 80% as a hard constraint, then minimise false positives within that constraint.

---

## Results

```
Classification Report (threshold = 0.4, test set):

              precision    recall  f1-score   support
       Legit       1.00      1.00      1.00     56,864
       Fraud       0.67      0.89      0.76         98

    accuracy                           1.00     56,962
   macro avg       0.83      0.94      0.88     56,962
weighted avg       1.00      1.00      1.00     56,962

Confusion Matrix:
                 Pred Legit   Pred Fraud
  Actual Legit     56,821          43      ← 43 false positives
  Actual Fraud         11          87      ← 11 missed frauds

ROC-AUC: 0.9827
```

---

## Retraining Pipeline (Week 8+)

Every reviewer verdict is stored in `reviewer_feedback` with `used_in_training=False`. A weekly job:

1. Pulls all unprocessed feedback
2. Re-labels transactions based on reviewer decisions
3. Retrains XGBoost on combined original + feedback data
4. Compares new model against current on holdout set
5. Promotes new model if recall improves

```bash
# Manual retraining (automated in production)
python3.12 ml/train.py --data notebooks/creditcard.csv
```

---

## Running Training

```bash
cd backend

# Full training run
python3.12 ml/train.py --data notebooks/creditcard.csv

# Output:
# 1. Loading dataset...    Rows: 284,807
# 2. Engineering features... 31 features
# 3. Splitting data...     Train: 227,845 | Test: 56,962
# 4. Scaling features...
# 5. Applying SMOTE...     After: 454,902 total
# 6. Training XGBoost...   Training complete.
# 7. Evaluating...         Recall: 0.8878 ✓
# 8. Saving model...       models/xgb_fraud_v1.joblib
```
