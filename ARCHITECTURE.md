# 📐 Architecture Deep Dive

## Overview

The fraud detection engine is built around three core principles:

1. **Latency over accuracy** — a score that arrives in 3ms is more useful than a perfect score that arrives in 300ms. Payment gateways timeout after ~100ms.
2. **Immutability** — ledger entries are never updated, only appended. Corrections use reversing entries.
3. **Idempotency** — every component handles duplicate events gracefully. A consumer restart should never double-score a transaction.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INGESTION LAYER                             │
│                                                                     │
│  Payment Gateway ──► Kafka Producer ──► transactions.raw topic      │
│  (producer.py)                          (partitioned by user_id)    │
└──────────────────────────────────────────────┬──────────────────────┘
                                               │
                                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SCORING LAYER                               │
│                                                                     │
│  Kafka Consumer ──► Feature Builder ──► XGBoost Model ──► Score    │
│  (consumer.py)      (features.py)       (predict.py)               │
│                          │                                          │
│                          ▼                                          │
│                     Redis Cache                                     │
│                     ├── velocity:{user_id}  (sorted set, TTL 25h)  │
│                     └── location:{user_id}  (hash, TTL 7d)         │
└──────────────────────────────────────────────┬──────────────────────┘
                                               │
                              ┌────────────────┴────────────────┐
                              │ score < 0.4                      │ score ≥ 0.4
                              ▼                                  ▼
┌──────────────────────────────────┐   ┌──────────────────────────────────┐
│         APPROVED PATH            │   │          FLAGGED PATH             │
│                                  │   │                                  │
│  → transactions table (approved) │   │  → transactions table (flagged)  │
│  → fraud_scores table            │   │  → fraud_scores table            │
│  → transactions.scored topic     │   │  → fraud_alerts table            │
└──────────────────────────────────┘   │  → fraud.alerts topic            │
                                       └──────────────────┬───────────────┘
                                                          │
                                                          ▼
                                       ┌──────────────────────────────────┐
                                       │       REVIEW LAYER               │
                                       │                                  │
                                       │  Dashboard ──► PATCH /v1/alerts  │
                                       │              ──► reviewer_feedback│
                                       │              ──► retraining data  │
                                       └──────────────────────────────────┘
```

---

## Data Flow: Transaction Lifecycle

### Step 1 — Transaction arrives
A payment event is published to `transactions.raw` with `user_id` as the partition key. Partitioning by `user_id` ensures all events for the same user land on the same partition, preserving ordering for velocity calculations.

### Step 2 — Feature building (Redis)
Before scoring, the feature builder queries Redis:
- `ZCOUNT velocity:{user_id} (now-3600) now` → transactions in last hour
- `ZCOUNT velocity:{user_id} (now-86400) now` → transactions in last 24h
- `GET location:{user_id}` → last known lat/lng → haversine distance

This takes **<1ms** per feature.

### Step 3 — Model inference
The feature vector is scaled using the same `StandardScaler` fitted during training, then passed to `XGBClassifier.predict_proba()`. The model returns a float between 0 and 1. Total model inference time: **1–2ms**.

### Step 4 — Threshold decision
```
score < 0.4  → approved
score ≥ 0.4  → flagged
```
The threshold was chosen by maximizing recall on the validation set while keeping false positive rate under 0.1%.

### Step 5 — Persistence
The consumer writes to Postgres in a single database transaction:
- `transactions` row (status = approved/flagged)
- `fraud_scores` row (score, features snapshot, latency)
- `fraud_alerts` row (if flagged, severity, SLA deadline)

The Kafka offset is committed **after** the DB write. This is the critical idempotency mechanism.

### Step 6 — Review
If flagged, the alert appears in the reviewer dashboard. The reviewer submits a verdict via `PATCH /v1/alerts/{id}/review`. The verdict is stored in `reviewer_feedback` for weekly model retraining.

---

## Kafka Topic Design

| Topic | Partitions | Retention | Key | Purpose |
|---|---|---|---|---|
| `transactions.raw` | 12 | 7 days | `user_id` | Raw payment events from gateway |
| `transactions.scored` | 12 | 30 days | `user_id` | Scored events for downstream consumers |
| `fraud.alerts` | 4 | 90 days | `alert_id` | Alert notifications |

Partitioning by `user_id` on the raw topic is critical — it ensures ordered delivery per user, which makes velocity features deterministic even under high throughput.

---

## Redis Data Structures

### Velocity (sorted set)
```
Key:   velocity:{user_id}
Type:  Sorted Set
Score: Unix timestamp (float)
Member: transaction_id (string)
TTL:   90,000 seconds (25 hours)

Query: ZCOUNT velocity:{user_id} {now - 3600} {now}
       → count of transactions in last hour
```

### Location (string/hash)
```
Key:   location:{user_id}
Type:  String (JSON)
Value: {"lat": 40.7128, "lon": -74.0060}
TTL:   604,800 seconds (7 days)
```

---

## Failure Modes and Recovery

| Failure | Behaviour |
|---|---|
| Consumer crashes mid-batch | Uncommitted offsets are replayed on restart; `kafka_offset` dedup prevents double-scoring |
| Redis unavailable | Feature builder returns zeros; scoring continues with degraded features |
| Postgres unavailable | Consumer logs error, does NOT commit Kafka offset; message is replayed |
| Model not loaded | API returns 500 immediately; consumer refuses to start |
| SLA breach | `escalate_alerts.py` job marks alerts as `escalated=True` |

---

## Sequence Diagram: Happy Path

```
Producer    Kafka      Consumer     Redis      XGBoost    Postgres
   │           │           │           │           │           │
   │──publish──►           │           │           │           │
   │           │──deliver──►           │           │           │
   │           │           │──query────►           │           │
   │           │           │◄──features─           │           │
   │           │           │──score────────────────►           │
   │           │           │◄──0.0043──────────────            │
   │           │           │──write────────────────────────────►
   │           │           │◄──ok──────────────────────────────
   │           │◄──commit──│           │           │           │
```
