# 📨 Kafka Pipeline

## Overview

Kafka sits between the payment gateway and the scoring service, decoupling ingestion from processing. This means the scoring service can be restarted, upgraded, or scaled without losing a single transaction.

---

## Topics

### `transactions.raw`
Raw payment events from the gateway. The source of truth.

```
Partitions:  12
Retention:   7 days
Key:         user_id (partitioned for ordered delivery per user)
Producer:    kafka_pipeline/producer.py
Consumer:    kafka_pipeline/consumer.py (group: fraud-scorer)
```

**Message format:**
```json
{
  "transaction_id": "uuid",
  "user_id":        "uuid",
  "merchant_id":    "uuid",
  "amount_cents":   150000,
  "currency":       "USD",
  "country_code":   "US",
  "occurred_at":    "2026-06-06T14:22:00Z",
  "lat":            40.7128,
  "lon":            -74.0060
}
```

---

### `transactions.scored`
Scored events published after model inference. Downstream consumers (analytics, notifications) subscribe here.

```
Partitions:  12
Retention:   30 days
Key:         user_id
Producer:    kafka_pipeline/consumer.py (after scoring)
```

**Message format:**
```json
{
  "transaction_id":  "uuid",
  "score":           0.8231,
  "verdict":         "flagged",
  "model_version":   "xgb-v1.0.0",
  "threshold_used":  0.4,
  "top_features": {
    "velocity_1h":      4.0,
    "geo_distance_km":  8420.5,
    "amount_log":       11.92
  },
  "scored_at": "2026-06-06T14:22:00Z"
}
```

---

### `fraud.alerts`
Alert notifications for flagged transactions. Could drive push notifications, SMS, or automated blocking.

```
Partitions:  4
Retention:   90 days
Key:         alert_id
```

---

## Producer (Payment Gateway Stub)

`kafka_pipeline/producer.py` simulates a payment gateway publishing transactions.

```bash
# Usage
cd backend
python3.12 kafka_pipeline/producer.py --count 100 --high-risk-pct 0.3

# Options
--count          Number of transactions to publish (default: 10)
--high-risk-pct  Fraction that are high-risk (default: 0.2)
```

**What makes a transaction "high-risk" in the stub:**
- Amount: $500–$10,000 (vs $5–$200 normal)
- Hour: 1–4am (vs 9am–6pm normal)
- Location: randomly chosen globally (vs common domestic locations)

---

## Consumer (Fraud Scoring)

`kafka_pipeline/consumer.py` is the core pipeline component.

```bash
cd backend
python3.12 kafka_pipeline/consumer.py
```

### Processing flow

```
Poll message from transactions.raw
         │
         ▼
Check kafka_offset in fraud_scores table
         │
    ┌────┴────┐
    │ exists? │
    └────┬────┘
         │ yes                    no
         ▼                        ▼
    SKIP (duplicate)      Build Redis features
                                  │
                                  ▼
                          Run XGBoost inference
                                  │
                                  ▼
                          Write to Postgres
                          ├── transactions
                          ├── fraud_scores
                          └── fraud_alerts (if flagged)
                                  │
                                  ▼
                          Publish to transactions.scored
                                  │
                                  ▼
                          Commit Kafka offset ← CRITICAL
```

### The offset commit pattern

```python
# Manual offset commit — the most important line in the consumer
consumer = KafkaConsumer(
    enable_auto_commit=False,   # ← never auto-commit
    ...
)

for message in consumer:
    try:
        with Session(engine) as db:
            process_message(message, db)
        consumer.commit()       # ← commit AFTER DB write succeeds
    except Exception as e:
        print(f"Error: {e}")
        # DO NOT commit — message will be replayed on restart
```

**Why this matters:** If the consumer crashes after writing to Postgres but before committing the offset, the message will be replayed on restart. The `kafka_offset` uniqueness check catches this duplicate and skips it.

---

## Idempotency

Every transaction in `fraud_scores` has a unique `kafka_offset`. Before processing:

```python
def is_duplicate(db, transaction_id, kafka_offset):
    existing = db.query(FraudScore).filter(
        FraudScore.transaction_id == transaction_id
    ).first()
    return existing is not None
```

If the same message is delivered twice (crash-recovery scenario), the second processing attempt finds the existing score and skips. **No transaction is ever scored twice.**

---

## Consumer Groups

The consumer runs under group `fraud-scorer`. Kafka tracks the last committed offset per group. Multiple consumer instances in the same group form a consumer group — Kafka distributes partitions across them automatically.

For this project, a single consumer instance handles all 12 partitions. In production, you'd scale to 12 consumer instances (one per partition) for parallelism.

---

## Failure Scenarios

| Scenario | Behaviour |
|---|---|
| Consumer crashes mid-message | Offset not committed → message replayed → `kafka_offset` dedup skips it |
| Postgres unavailable | Consumer logs error, does not commit → message replayed when Postgres recovers |
| Redis unavailable | Features default to 0 → scoring continues with degraded accuracy |
| Kafka broker unavailable | Consumer retries with exponential backoff → no data loss |
| Message with invalid format | Error logged → message skipped (dead-letter queue recommended in production) |

---

## Monitoring

Watch the consumer output for real-time stats:

```
Loading ML model...
Model loaded: xgb-v1.0.0 (31 features)
Listening on 'transactions.raw' (group: fraud-scorer)...

Received offset=0 txn=20bbf198...
  [✓  approved] 20bbf198... score=0.0043 latency=26ms

Received offset=1 txn=ee172851...
  [🚨 FLAGGED]  ee172851... score=0.7821 latency=3ms
```

Key metrics to monitor in production:
- Consumer lag (offset behind latest)
- Processing latency per message
- Flagged rate (% of transactions flagged)
- Error rate
