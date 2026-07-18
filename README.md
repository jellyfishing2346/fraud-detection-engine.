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
[![XGBoost](https://img.shields.io/badge/XGBoost-Recall_89%25-orange?style=flat-square)](https://xgboost.readthedocs.io)
[![Redis](https://img.shields.io/badge/Redis-Velocity_Features-red?style=flat-square&logo=redis)](https://redis.io)
[![Kafka](https://img.shields.io/badge/Kafka-KRaft_Mode-231F20?style=flat-square&logo=apache-kafka)](https://kafka.apache.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql)](https://postgresql.org)

[**▶ Live Dashboard**](https://tranquil-lokum-370120.netlify.app/) · [**API Docs**](https://fraud-detection-engine-ozjc.onrender.com/docs) · [**📖 Docs**](docs/) · [**🚀 Quickstart**](#quickstart) · [**🏗 Architecture**](#architecture)

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
| 🖥 **Reviewer Dashboard** | https://sparkling-brioche-94b5f2.netlify.app/dashboard.html |
| 📡 **API** | https://fraud-detection-engine-ozjc.onrender.com |
| 📖 **API Docs** | https://fraud-detection-engine-ozjc.onrender.com/docs |
| ❤️ **Health Check** | https://fraud-detection-engine-ozjc.onrender.com/health |

> **Note:** API is hosted on Render free tier — first request after inactivity may take ~50 seconds to wake up.

![Fraud Detection Engine Demo](<Fraud Review Console Walkthrough.gif>)

---

## Performance

| Metric | Result |
|---|---|
| 🎯 Fraud recall | **89%** — catches 89 of every 100 real fraud cases |
| 📈 ROC-AUC | **0.98** — near-perfect class separation |
| ⚡ Scoring latency (warm) | **2–3ms** — Redis feature cache |
| ⚡ Scoring latency (cold) | **27ms** — first request |
| 🔍 False positive rate | **0.08%** — 8 in 10,000 legit transactions flagged |
| 📦 Training dataset | **284,807 transactions** |

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
                             │   sparkling-brioche-94b5f2.netlify   │
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

### 3. Train the model

Download [`creditcard.csv`](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) → place in `backend/notebooks/`

```bash
cd backend
python3.12 ml/train.py --data notebooks/creditcard.csv
```

### 4. Seed test data

```bash
python3.12 scripts/seed.py
# Writes 1000 transactions and ~80 fraud alerts
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
| https://sparkling-brioche-94b5f2.netlify.app/dashboard.html | Live reviewer dashboard |
| https://fraud-detection-engine-ozjc.onrender.com/docs | Live API docs |

---

## Documentation

| Document | Description |
|---|---|
| [📐 Architecture](docs/ARCHITECTURE.md) | System design, data flow, component decisions |
| [🤖 ML Model](docs/ML_MODEL.md) | Feature engineering, training, threshold tuning |
| [🗄 Database Schema](docs/DATABASE.md) | Table design, relationships, indexing |
| [📡 API Reference](docs/API.md) | All endpoints with request/response examples |
| [📨 Kafka Pipeline](docs/KAFKA.md) | Topics, consumers, idempotency, failure handling |
| [🔧 Development Guide](docs/DEVELOPMENT.md) | Local setup, linting, testing |
| [🧠 Technical Decisions](docs/DECISIONS.md) | Why each technology was chosen |

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
| **Week 2** | XGBoost training · SMOTE oversampling · recall 0.89 |
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
