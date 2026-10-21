<div align="center">

```
███████╗██████╗  █████╗ ██╗   ██╗██████╗
██╔════╝██╔══██╗██╔══██╗██║   ██║██╔══██╗
█████╗  ██████╔╝███████║██║   ██║██║  ██║
██╔══╝  ██╔══██╗██╔══██║██║   ██║██║  ██║
██║     ██║  ██║██║  ██║╚██████╔╝██████╔╝
╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝

D E T E C T I O N   E N G I N E
```

**Real-time transaction fraud scoring at production scale**

[![Python](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![XGBoost](https://img.shields.io/badge/XGBoost-v2-orange?style=flat-square)](ML_MODEL.md)
[![Redis](https://img.shields.io/badge/Redis-Velocity_Features-red?style=flat-square&logo=redis)](https://redis.io)
[![Kafka](https://img.shields.io/badge/Kafka-KRaft_Mode-231F20?style=flat-square&logo=apache-kafka)](https://kafka.apache.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql)](https://postgresql.org)

[**▶ Live Dashboard**](https://superlative-sorbet-ea6ee1.netlify.app) · [**API Docs**](https://fraud-detection-engine-ozjc.onrender.com/docs) · [**📖 Docs**](#documentation) · [**🚀 Quickstart**](#quickstart) · [**🏗 Architecture**](#architecture)

</div>

---

## What is this?

A **production-grade fraud detection system** built from scratch — the kind of infrastructure that sits at the heart of every bank and payments company. It scores transactions in real time using machine learning, streams events through Kafka, caches features in Redis, and surfaces flagged transactions to human reviewers through a custom dashboard.

Built solo over 8 weeks as a deep-dive into fintech engineering.

```
Transaction arrives → Kafka → ML Scoring (2ms) → Approved ✓
                                               └→ Flagged 🚨 → Reviewer Dashboard
```

---

## Live Demo

| | URL |
|---|---|
| 🖥 **Reviewer Dashboard** | https://superlative-sorbet-ea6ee1.netlify.app |
| 📡 **API** | https://fraud-detection-engine-ozjc.onrender.com |
| 📖 **API Docs** | https://fraud-detection-engine-ozjc.onrender.com/docs |
| ❤️ **Health Check** | https://fraud-detection-engine-ozjc.onrender.com/health |

> **Note:** API is hosted on Render free tier — first request after inactivity may take ~50 seconds to wake up.

![Fraud Detection Engine Demo](assets/demo.gif)

---

## Performance

Model v2, measured on held-out **synthetic** data (40,000 transactions). These describe how well the model learns the simulation, not real-world performance; see [ML_MODEL.md](ML_MODEL.md).

| Metric | Result |
|---|---|
| 🎯 Fraud recall | **72%** at the 0.4 threshold |
| 🔍 Precision | **51%** — about half of flagged transactions are fraud |
| 🔍 False positive rate | **2.2%** of legitimate transactions flagged for review |
| 📈 ROC-AUC / PR-AUC | **0.94 / 0.74** |
| ⚡ Scoring latency (warm) | **2–3ms** — Redis feature cache |
| ⚡ Scoring latency (cold) | **27ms** — first request |

The original v1 model reached 89% recall and 0.98 ROC-AUC on the Kaggle credit card dataset, but relied on features the live API can't compute, so it couldn't flag real requests. [ML_MODEL.md](ML_MODEL.md) explains the switch.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     PAYMENT GATEWAY                         │
│               (kafka_pipeline/producer.py)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │  transaction events
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              KAFKA: transactions.raw                        │
│         partitioned by user_id · retention: 7d              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              ML SCORING SERVICE (FastAPI)                   │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────────────────┐     │
│  │  Redis Cache     │  │     XGBoost Model            │     │
│  │  velocity_1h ────┼─►│  score = f(                  │     │
│  │  velocity_24h    │  │    amount_log,               │     │
│  │  geo_distance_km │  │    hour_of_day,              │     │
│  │  is_new_location │  │    velocity_1h,              │     │
│  └──────────────────┘  │    geo_distance_km ...       │     │
│                        └──────────────────────────────┘     │
└──────────┬─────────────────────────────┬────────────────────┘
           │ score < 0.4                 │ score ≥ 0.4
           ▼                             ▼
┌──────────────────┐        ┌────────────────────────────┐
│  APPROVED        │        │  FLAGGED                   │
│  → ledger DB     │        │  → fraud_alerts table      │
└──────────────────┘        └──────────────┬─────────────┘
                                           │
                                           ▼
                             ┌──────────────────────────────────────┐
                             │   REVIEWER DASHBOARD                 │
                             │   superlative-sorbet-ea6ee1.netlify  │
                             └──────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **API** | FastAPI + Uvicorn | Async, auto-generates OpenAPI docs |
| **ML Model** | XGBoost | 3ms inference, interpretable, strong on tabular data |
| **Feature cache** | Redis sorted sets | O(log n) velocity queries, auto-expiring TTL |
| **Event streaming** | Apache Kafka (KRaft) | Durable, ordered, replayable — no Zookeeper |
| **Database** | PostgreSQL 16 | ACID guarantees for financial ledger data |
| **Frontend** | Vanilla JS + HTML | Served by FastAPI — no build step |
| **Infrastructure** | Docker Compose | Reproducible local environment |
| **Linting** | Ruff | Runs on every commit via pre-commit hooks |

---

## Quickstart

> **Prerequisites:** Docker Desktop · Python 3.11+

### 1. Clone and configure

```bash
git clone https://github.com/jellyfishing2346/fraud-detection-engine..git
cd fraud-detection-engine.
cp .env.example .env
```

### 2. Start infrastructure

```bash
cd infra && docker compose up -d
docker compose ps   # wait until postgres and redis show (healthy)
```

### 3. Train the model (optional)

The trained model ships in `backend/models/`. To retrain it (a few seconds, deterministic):

```bash
cd backend
python3.12 -m ml.train_v2
```

The model uses only features the API computes at request time, trained on synthetic data. See [ML_MODEL.md](ML_MODEL.md) for why, and for the legacy Kaggle-trained v1.

### 4. Seed test data

```bash
python3.12 scripts/seed.py          # add demo data
python3.12 scripts/seed.py --reset  # replace ALL existing transactions and alerts
# Simulates 30 days of activity for 60 users (~3,700 transactions), scored by the
# real model; ~160 get flagged, older alerts closed with reviewer verdicts
```

### 5. Start the API

```bash
export DATABASE_URL="postgresql://fraud_user:fraud_pass@127.0.0.1:5432/fraud_db"
python3.12 -m uvicorn main:app --reload
```

### 6. Open the dashboard

| URL | Description |
|---|---|
| http://localhost:8000/dashboard | Local reviewer dashboard |
| http://localhost:8000/docs | Local API docs |
| https://superlative-sorbet-ea6ee1.netlify.app | Live reviewer dashboard |
| https://fraud-detection-engine-ozjc.onrender.com/docs | Live API docs |

---

## Documentation

| Document | Description |
|---|---|
| [📐 Architecture](ARCHITECTURE.md) | System design, data flow, component decisions |
| [🤖 ML Model](ML_MODEL.md) | Feature engineering, training, threshold tuning |
| [🗄 Database Schema](DATABASE.md) | Table design, relationships, indexing |
| [📡 API Reference](API.md) | All endpoints with request/response examples |
| [📨 Kafka Pipeline](KAFKA.md) | Topics, consumers, idempotency, failure handling |
| [🔧 Development Guide](DEVELOPMENT.md) | Local setup, linting, testing |

---

## Kafka Pipeline

```bash
# Terminal 1 — consumer: scores transactions from Kafka
cd backend && python3.12 kafka_pipeline/consumer.py

# Terminal 2 — producer: simulate payment gateway
cd backend && python3.12 kafka_pipeline/producer.py --count 100 --high-risk-pct 0.3
```

## Tests

```bash
cd backend && python3.12 -m pytest tests/ -v
# 6/6 passing
```

---

## Build Log

| Week | Milestone |
|---|---|
| **Week 1** | Docker stack · PostgreSQL schema · project structure |
| **Week 2** | XGBoost training (v1, Kaggle) · SMOTE oversampling · recall 0.89 |
| **Week 3** | FastAPI scoring API · model inference · 41ms cold latency |
| **Week 4** | Redis velocity features · haversine geo-distance · 2ms warm |
| **Week 5** | pytest suite 6/6 · SLA escalation job · branch protection |
| **Week 6** | Kafka producer + consumer · idempotent offset handling |
| **Week 7** | Reviewer dashboard · verdict submission · CORS middleware |
| **Week 8** | Seed data · full documentation suite · deployed to Render + Netlify |

---

<div align="center">

Built by **[@jellyfishing2346](https://github.com/jellyfishing2346)** · 8 weeks · Solo

</div>
