# Free Tier Setup Guide

This guide shows how to set up the fraud detection engine using free services:
- **Supabase** (Free PostgreSQL - 500MB)
- **Upstash** (Free Redis with Redis Streams - 10,000 commands/day)
- **Render** (Free FastAPI hosting - sleeps when inactive)

## Step 1: Set up Supabase (PostgreSQL)

1. Go to [supabase.com](https://supabase.com) and sign up for free
2. Create a new project:
   - Name: `fraud-detection-engine`
   - Database password: (generate a strong password)
   - Region: Choose closest to you
3. Wait for the project to be created (~2 minutes)
4. Go to Settings → Database → Connection string
5. Copy the **URI** format connection string
6. Run your database schema on Supabase:

```bash
# In your backend directory
psql "YOUR_SUPABASE_CONNECTION_STRING" < db/schema.sql
```

## Step 2: Set up Upstash (Redis + Redis Streams)

1. Go to [upstash.com](https://upstash.com) and sign up for free
2. Create a new Redis database:
   - Name: `fraud-detection-redis`
   - Region: Choose closest to you
3. Once created, go to Details → REST API
4. Copy the **REST URL** (looks like `https://xxx.upstash.io`)
5. Copy the **REST Token**

## Step 3: Update your .env file

Update your `.env` file with the new service credentials:

```bash
# ─── Database (Supabase) ─────────────────────────────────────
DATABASE_URL=postgresql://postgres.xxx:PASSWORD@aws-0-region.pooler.supabase.com:6543/postgres

# ─── Redis (Upstash) ─────────────────────────────────────────
REDIS_URL=rediss://default:PASSWORD@xxx.upstash.io:6379

# ─── Redis Streams ───────────────────────────────────────────
REDIS_STREAM_RAW=transactions.raw
REDIS_STREAM_SCORED=transactions.scored
REDIS_CONSUMER_GROUP=fraud-scorer
REDIS_CONSUMER_NAME=fraud-scorer-1

# ─── ML Model ───────────────────────────────────────────────
MODEL_PATH=models/xgb_fraud_v1.joblib
FRAUD_SCORE_THRESHOLD=0.4

# ─── App ─────────────────────────────────────────────────────
APP_ENV=production
SECRET_KEY=change-this-to-a-random-string-in-production
API_PORT=8000
```

## Step 4: Test locally with new services

Start the Redis Streams consumer:

```bash
cd backend
python3.12 redis_pipeline/consumer.py
```

In another terminal, produce transactions:

```bash
cd backend
python3.12 redis_pipeline/producer.py --count 20 --high-risk-pct 0.3
```

## Step 5: Deploy to Render

1. Go to [render.com](https://render.com) and connect your GitHub repo
2. Create a new **Web Service**:
   - Name: `fraud-detection-api`
   - Environment: `Python 3`
   - Build Command: `cd backend && pip install -r requirements.txt`
   - Start Command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Add environment variables from your `.env` file
4. Deploy!

## Key Differences from Kafka

### Kafka → Redis Streams Changes:

1. **Producer**: `kafka_pipeline/producer.py` → `redis_pipeline/producer.py`
2. **Consumer**: `kafka_pipeline/consumer.py` → `redis_pipeline/consumer.py`
3. **Message format**: Redis Streams use key-value pairs instead of JSON
4. **Idempotency**: Uses message IDs instead of Kafka offsets
5. **Consumer groups**: Redis Streams have similar consumer group semantics

### Free Tier Limitations:

- **Supabase**: 500MB database storage (plenty for your use case)
- **Upstash**: 10,000 Redis commands/day (sufficient for development/testing)
- **Render**: Free tier sleeps after 15 minutes inactivity (first request takes ~50s to wake)

## Cost Comparison

| Service | Free Tier | Paid Tier |
|---------|-----------|------------|
| Supabase PostgreSQL | 500MB | $25/month for 8GB |
| Upstash Redis | 10K commands/day | $0.20/10K commands |
| Render | Free (sleeps) | $7/month (always on) |
| **Total** | **$0/month** | **~$32/month** |

## Running the Pipeline

### Local Development:

```bash
# Terminal 1: Start Redis Streams consumer
cd backend && python3.12 redis_pipeline/consumer.py

# Terminal 2: Produce transactions
cd backend && python3.12 redis_pipeline/producer.py --count 100 --high-risk-pct 0.2
```

### Production (on Render):

The FastAPI app will handle individual transaction scoring via HTTP endpoints. For continuous processing, you can:

1. Run the consumer as a separate worker process on Render
2. Use a cron job to periodically produce test transactions
3. Connect to real payment gateway (replace producer)

## Troubleshooting

### Redis Connection Issues:
- Ensure your Upstash Redis URL starts with `rediss://` (SSL required)
- Check that your REST token is correct
- Verify Upstash database is in the same region as your app

### Supabase Connection Issues:
- Use the "URI" format connection string from Supabase dashboard
- Ensure your database password is correct
- Check that your IP is allowed in Supabase settings

### Render Deployment Issues:
- Make sure all environment variables are set in Render dashboard
- Check that the build command installs all dependencies
- Verify the start command uses `$PORT` environment variable

## Next Steps

1. Test the Redis Streams pipeline locally
2. Deploy to Render with Supabase + Upstash
3. Monitor free tier usage to avoid limits
4. Consider upgrading to paid tiers if you hit limits
