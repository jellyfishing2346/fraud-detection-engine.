# Quick Ngrok Setup Guide

Since we encountered some Python dependency issues, here's the manual setup that will work:

## Step 1: Fix Python Dependencies

First, we need to fix the scikit-learn architecture issue:

```bash
# Uninstall the incompatible scikit-learn
pip uninstall scikit-learn -y

# Reinstall with correct architecture
pip install scikit-learn --no-cache-dir
```

## Step 2: Start Your FastAPI App

```bash
cd /Users/test/fraud-detection-engine./backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Keep this terminal open - you should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

## Step 3: Start Ngrok (New Terminal)

Open a new terminal and run:

```bash
ngrok http 8000
```

You'll see something like:
```
Forwarding  https://abc123.ngrok.io -> http://localhost:8000
```

## Step 4: Use Your Live URL

Copy the ngrok URL (e.g., `https://abc123.ngrok.io`) and use it:
- **API URL**: `https://abc123.ngrok.io/v1/score`
- **Dashboard**: `https://abc123.ngrok.io/dashboard`
- **Health**: `https://abc123.ngrok.io/health`

## Step 5: Update Your Frontend

Update your frontend to use the ngrok URL:
```javascript
const API_URL = 'https://your-ngrok-url.ngrok.io';
```

## Troubleshooting

### If you get "Module not found" errors:
```bash
cd /Users/test/fraud-detection-engine.
pip install -r requirements.txt
```

### If scikit-learn has architecture issues:
```bash
pip uninstall scikit-learn -y
pip install scikit-learn --no-cache-dir --force-reinstall
```

### If port 8000 is busy:
```bash
lsof -ti:8000 | xargs kill -9
```

## That's It!

Your app is now live and accessible from anywhere with the ngrok URL!
