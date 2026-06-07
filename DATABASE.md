# 🗄 Database Schema

## Overview

Four tables form the core data model. The design prioritises **immutability** and **auditability** — financial data is never deleted or updated, only appended.

```
transactions
    │
    ├──── fraud_scores (1:1 — one score per transaction)
    │         │
    │         └──── fraud_alerts (1:1 — one alert per flagged score)
    │                   │
    │                   └──── reviewer_feedback (1:many — one alert, many verdicts possible)
    │
    └──── (ledger entry for approved transactions)
```

---

## Table: `transactions`

The immutable record of every payment event. Never updated after insert.

```sql
CREATE TABLE transactions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,
    merchant_id         UUID,
    amount_cents        BIGINT NOT NULL,       -- never float: $15.99 = 1599
    currency            CHAR(3) NOT NULL,      -- ISO 4217: USD, EUR, GBP
    country_code        CHAR(2),               -- ISO 3166: US, GB, FR
    ip_address          INET,
    device_fingerprint  TEXT,
    occurred_at         TIMESTAMPTZ NOT NULL,  -- event time, NOT insert time
    status              TEXT NOT NULL,         -- pending | approved | blocked
    kafka_offset        BIGINT UNIQUE          -- idempotency: skip if seen
);

CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_occurred_at ON transactions(occurred_at);
```

### Key decisions

**`amount_cents` is BIGINT, not FLOAT**
Never store money as a floating point number. `0.1 + 0.2 = 0.30000000000000004` in IEEE 754. Store cents as an integer: $15.99 = `1599`. Convert to dollars only for display.

**`occurred_at` is event time, not insert time**
A transaction that happened at 2:15am but was processed at 2:16am should record `2:15am`. Using `NOW()` at insert time would corrupt velocity and time-of-day features.

**`kafka_offset` uniqueness constraint**
Before inserting, the consumer checks if `kafka_offset` already exists. If yes, the transaction was already processed — skip it. This makes the consumer idempotent on replay.

---

## Table: `fraud_scores`

One row per transaction scored. Stores the model output and the features used at score time.

```sql
CREATE TABLE fraud_scores (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id   UUID NOT NULL REFERENCES transactions(id),
    score            NUMERIC(5,4) NOT NULL,      -- 0.0000 to 1.0000
    threshold_used   NUMERIC(5,4) NOT NULL,
    model_version    TEXT NOT NULL,              -- "xgb-v1.0.0"
    feature_snapshot JSONB,                      -- features at score time
    scored_at        TIMESTAMPTZ DEFAULT NOW(),
    latency_ms       INTEGER
);
```

### Why store `feature_snapshot`?

Features change over time — a user's velocity at 2pm is different at 3pm. If we recalculate features after the fact, we get different numbers than what the model actually saw. Storing the snapshot means:
- Reviewers see exactly what drove the score
- Debugging is reproducible
- Model behaviour is auditable

### Why store `model_version`?

Different model versions make different decisions. When the model is retrained, old scores remain attributed to the model that produced them. This is essential for tracking model drift over time.

---

## Table: `fraud_alerts`

Created only for transactions with score ≥ threshold. Drives the reviewer workflow.

```sql
CREATE TABLE fraud_alerts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL REFERENCES transactions(id),
    fraud_score_id UUID NOT NULL REFERENCES fraud_scores(id),
    severity       TEXT NOT NULL,       -- low | medium | high
    state          TEXT NOT NULL,       -- open | in_review | closed
    assigned_to    UUID,                -- analyst user_id, nullable
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    sla_deadline   TIMESTAMPTZ NOT NULL, -- created_at + 4 hours
    escalated      BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_fraud_alerts_created_at ON fraud_alerts(created_at);
```

### Severity mapping

```
score 0.40 – 0.59 → low
score 0.60 – 0.79 → medium
score 0.80 – 1.00 → high
```

### SLA design

Every alert has a 4-hour SLA. The `escalate_alerts.py` job runs periodically and sets `escalated=True` on any open alert past its deadline. The dashboard highlights escalated alerts in red.

### State machine

```
         ┌─────────┐
         │  open   │◄──── created when score ≥ threshold
         └────┬────┘
              │ reviewer claims alert
              ▼
       ┌────────────┐
       │  in_review │
       └─────┬──────┘
             │ reviewer submits verdict
             ▼
         ┌────────┐
         │ closed │
         └────────┘
```

Note: the dashboard currently moves directly from `open` to `closed`. `in_review` is reserved for multi-analyst workflows.

---

## Table: `reviewer_feedback`

Records every analyst decision. Feeds the retraining pipeline.

```sql
CREATE TABLE reviewer_feedback (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alert_id         UUID NOT NULL REFERENCES fraud_alerts(id),
    reviewer_id      UUID NOT NULL,
    verdict          TEXT NOT NULL,     -- confirmed | false_positive
    notes            TEXT,
    reviewed_at      TIMESTAMPTZ DEFAULT NOW(),
    used_in_training BOOLEAN DEFAULT FALSE
);
```

### Retraining signal

The `used_in_training` flag tracks which feedback rows have been incorporated into the model. A weekly batch job:
1. Selects rows where `used_in_training = FALSE`
2. Uses them to augment the training dataset
3. Sets `used_in_training = TRUE` after the model is retrained

---

## Indexes

```sql
-- High-cardinality lookups
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_transactions_occurred_at ON transactions(occurred_at DESC);
CREATE INDEX idx_fraud_alerts_created_at ON fraud_alerts(created_at DESC);
CREATE INDEX idx_fraud_alerts_state ON fraud_alerts(state);
```

The `created_at DESC` indexes support the most common query pattern — fetching the most recent alerts first.

---

## Money Rule

**Always store money as integer cents. Never use FLOAT or DOUBLE.**

```python
# ✅ Correct
amount_cents = 1599       # $15.99

# ❌ Wrong
amount = 15.99            # floating point representation error
amount = Decimal("15.99") # correct but unnecessary — just use cents

# Display conversion (Python)
display = f"${amount_cents / 100:.2f}"   # "$15.99"
```
