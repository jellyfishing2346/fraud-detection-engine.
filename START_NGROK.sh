#!/bin/bash

echo "🚀 Starting Fraud Detection Engine with ngrok..."

# Kill any existing processes on port 8000
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Start the FastAPI app in background
echo "📡 Starting FastAPI server on port 8000..."
cd /Users/test/fraud-detection-engine./backend
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for API to start
echo "⏳ Waiting for API to start..."
sleep 5

# Start ngrok
echo "🌐 Starting ngrok tunnel..."
ngrok http 8000
