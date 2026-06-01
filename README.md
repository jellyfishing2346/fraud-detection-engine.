# Fraud Detection Engine

A real-time transaction fraud scoring system built with FastAPI, XGBoost, Kafka, Redis, and PostgreSQL.

## Architecture

```
Payment Gateway → Kafka (transactions.raw) → ML Scoring Service → Kafka (transactions.scored)
                                                                 ↓               ↓
                                                           Ledger DB      Fraud Alert Queue
                                                                                 ↓
                                                                       React Reviewer Dashboard
```

## Tech stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python) |
| ML model | XGBoost + scikit-learn |
| Feature cache | Redis (sorted sets for velocity) |
| Message broker | Apache Kafka |
| Database | PostgreSQL 16 |
| Frontend | React |

## Quickstart

### Prerequisites
- Docker Desktop
- Python 3.11+
- Node.js 18+ (for the dashboard, week 7)

### 1. Clone and configure

```bash
git clone https://github.com/YOUR_USERNAME/fraud-detection-engine.git
cd fraud-detection-engine
cp .env.example .env   # edit .env with your values
```

### 2. Start the infrastructure

```bash
cd infra
docker compose up -d
```

Verify everything is running:
```bash
docker compose ps   # all services should show "healthy"
```

### 3. Install Python dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Create database tables

```bash
python db/models.py
```

### 5. Run the API

```bash
uvicorn main:app --reload
# Visit http://localhost:8000/docs for the interactive API docs
```

## Generating the model

```bash
# Download the dataset from Kaggle first:
# https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
# Place creditcard.csv in notebooks/

cd backend
python ml/train.py
# Saves model to models/xgb_fraud_v1.joblib
```

## Project structure

```
fraud-detection-engine/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── api/routes/          # score.py, alerts.py
│   ├── ml/                  # train.py, features.py, predict.py
│   ├── db/                  # SQLAlchemy models, Alembic migrations
│   ├── kafka/               # producer.py, consumer.py
│   └── requirements.txt
├── frontend/                # React reviewer dashboard
├── notebooks/               # EDA and training notebooks
├── infra/
│   └── docker-compose.yml   # Postgres, Redis, Kafka
├── scripts/
│   └── seed.py              # Load test transactions
└── .env.example
```

## Build log

| Week | What was built |
|---|---|
| 1 | Docker stack, Postgres schema, dataset exploration |
| 2 | Feature engineering, XGBoost training, threshold tuning |
| 3 | FastAPI scoring endpoint, model inference |
| 4 | Redis velocity features, latency optimisation |
| 5 | Alert creation, reviewer verdict API |
| 6 | Kafka pipeline, idempotent consumer |
| 7 | React reviewer dashboard |
| 8 | Seed data, documentation, demo video |

## Demo

*Coming week 8 — Loom link here*
