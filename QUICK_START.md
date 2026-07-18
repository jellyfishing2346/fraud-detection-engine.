# Quick Start - Get Your Live URL

## ✅ Your Server is Running!
Your FastAPI server is running successfully on `http://localhost:8000`

## 🚀 Get Your Live URL (2 Steps)

### Step 1: Open a New Terminal Window

### Step 2: Run This Command:
```bash
ngrok http 8000
```

## 📋 What You'll See:
```
ngrok by @inconshreveable

Session Status                online
Account                       your-name
Version                       3.x.x
Region                        United States
Forwarding                    https://abc123.ngrok.io -> http://localhost:8000
```

## 🎯 Your Live URLs:
Copy the ngrok URL (e.g., `https://abc123.ngrok.io`) and use:

- **Health Check**: `https://abc123.ngrok.io/health`
- **API Docs**: `https://abc123.ngrok.io/docs`
- **Score API**: `https://abc123.ngrok.io/v1/score`
- **Alerts API**: `https://abc123.ngrok.io/v1/alerts`
- **Dashboard**: `https://abc123.ngrok.io/dashboard`

## 🧪 Test Your Live API:
```bash
# Test health endpoint
curl https://your-ngrok-url.ngrok.io/health

# Should return: {"status":"ok","version":"0.1.0"}
```

## 💡 Tips:
- Keep both terminals open (one for server, one for ngrok)
- The ngrok URL changes each time you restart ngrok
- Your app is now accessible from anywhere!

## ❓ If you see "Not Found":
- Make sure you're using the full ngrok URL
- Include the endpoint path (e.g., `/health`, `/docs`)
- The root URL `/` returns 404 (this is normal)

## Done! Your fraud detection API is now live! 🎉
