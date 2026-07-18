# Railway.app Deployment Guide

**Free deployment option for the Fraud Detection Engine**

## Why Railway?

- **Free tier**: $5 credit/month (enough for small apps)
- **No credit card required** for sign-up
- **Always-on**: Unlike Render, Railway apps don't sleep
- **Easy deployment**: GitHub integration with auto-deploys
- **Perfect for**: FastAPI + ML models

## Prerequisites

1. Railway account (free at [railway.app](https://railway.app))
2. GitHub repository with your code
3. Supabase database (free tier)
4. Upstash Redis (free tier)

## Quick Setup

### 1. Install Railway CLI

```bash
npm install -g railway
# or
brew install railway
```

### 2. Login to Railway

```bash
railway login
```

### 3. Initialize project

```bash
cd /Users/test/fraud-detection-engine.
railway init
```

### 4. Deploy

```bash
railway up
```

## Environment Variables

Add these in Railway dashboard:

```bash
# Database (Supabase)
DATABASE_URL=postgresql://postgres.xxx:PASSWORD@aws-0-region.pooler.supabase.com:6543/postgres

# Redis (Upstash)
REDIS_URL=rediss://default:PASSWORD@xxx.upstash.io:6379

# Redis Streams
REDIS_STREAM_RAW=transactions.raw
REDIS_STREAM_SCORED=transactions.scored
REDIS_CONSUMER_GROUP=fraud-scorer
REDIS_CONSUMER_NAME=fraud-scorer-1

# ML Model
MODEL_PATH=models/xgb_fraud_v1.joblib
FRAUD_SCORE_THRESHOLD=0.4

# App
APP_ENV=production
SECRET_KEY=change-this-to-a-random-string-in-production
API_PORT=8000
```

## Railway Configuration Files

- `railway.toml` - Railway build and deploy settings
- `Procfile` - Process management
- `.railway/start.sh` - Custom startup script

## Troubleshooting

### Build Failures
- Check Railway logs for specific errors
- Ensure all dependencies are in requirements.txt
- Verify Python version compatibility

### Runtime Errors
- Check environment variables are set correctly
- Verify database and Redis connections
- Check Railway logs for startup errors

### Out of Credits
- Railway provides $5/month free credit
- Monitor usage in Railway dashboard
- Free tier is usually sufficient for development

## Alternative: Manual Setup via Dashboard

If CLI doesn't work, use Railway dashboard:

1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository
5. Configure build settings:
   - Build Command: `cd backend && pip install -r requirements.txt`
   - Start Command: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables
7. Deploy!

## Monitoring

- View logs in Railway dashboard
- Monitor resource usage
- Set up alerts for free tier usage

## Next Steps

1. Deploy to Railway
2. Test the API endpoints
3. Monitor free tier usage
4. Set up Supabase and Upstash if not already done
