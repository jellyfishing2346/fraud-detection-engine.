# Free & Cheap Deployment Options

When Railway's $5 free credit runs out, here are sustainable alternatives:

## 1. Ngrok Self-Hosting (100% Free)

**Best for: Testing, demos, personal use**

### How it works:
Run your app locally and expose it to the internet via ngrok tunnel.

### Setup:

```bash
# Install ngrok
brew install ngrok

# Start your FastAPI app locally
cd /Users/test/fraud-detection-engine./backend
python3.12 -m uvicorn main:app --host 0.0.0.0 --port 8000

# In another terminal, expose it
ngrok http 8000
```

You'll get a URL like: `https://abc123.ngrok.io`

### Pros:
- **Completely free**
- **No server management**
- **Instant setup**
- **HTTPS included**

### Cons:
- **Computer must stay on**
- **Dynamic URL changes on restart**
- **Not for production**
- **Limited bandwidth on free tier**

### Setup your frontend:
Update your frontend to use the ngrok URL:
```javascript
const API_URL = 'https://your-ngrok-url.ngrok.io';
```

---

## 2. Oracle Cloud Free Tier (Best Free Server)

**Best for: Always-on production app**

### What you get:
- **2 ARM-based VMs**: 24GB RAM, 4 OCPU each
- **200GB storage**
- **Truly free forever** (not a trial)
- **No credit card required** for verification

### Setup Steps:

1. **Create Oracle Cloud Account**
   - Go to [oracle.com/cloud/free](https://oracle.com/cloud/free)
   - Sign up (requires phone verification)
   - No credit card needed

2. **Create Compute Instance**
   - Dashboard → Compute → Instances
   - Click "Create Instance"
   - Choose "Always Free" tier
   - Image: Ubuntu 22.04
   - Shape: VM.Standard.E2.1.Micro (free tier)

3. **Connect to Server**
   ```bash
   ssh -i your-key.pem ubuntu@your-instance-ip
   ```

4. **Install Dependencies**
   ```bash
   sudo apt update
   sudo apt install python3.12 python3-pip git -y
   git clone https://github.com/jellyfishing2346/fraud-detection-engine.
   cd fraud-detection-engine.
   pip3 install -r requirements.txt
   ```

5. **Setup Environment Variables**
   ```bash
   nano .env
   # Add your DATABASE_URL, REDIS_URL, etc.
   ```

6. **Run with Systemd (Auto-restart)**
   ```bash
   sudo nano /etc/systemd/system/fraud-api.service
   ```

   Add this content:
   ```ini
   [Unit]
   Description=Fraud Detection API
   After=network.target

   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/fraud-detection-engine.
   Environment="PATH=/usr/local/bin:/usr/bin:/bin"
   ExecStart=/usr/local/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl enable fraud-api
   sudo systemctl start fraud-api
   ```

### Pros:
- **Truly free forever**
- **Always-on server**
- **Full control**
- **Enough power for ML models**

### Cons:
- **More complex setup**
- **Requires Linux knowledge**
- **Oracle account required**

---

## 3. DigitalOcean ($4/month)

**Best for: Cheap, reliable production**

### What you get:
- **1GB RAM, 1 vCPU, 25GB SSD**
- **Unlimited bandwidth**
- **99.99% uptime SLA**
- **Easy management**

### Setup Steps:

1. **Create DigitalOcean Account**
   - Go to [digitalocean.com](https://digitalocean.com)
   - Add $5 (credit card required)
   - Create droplet

2. **Create Droplet**
   - Choose "Basic" plan
   - $4/month: 1GB RAM, 1 vCPU
   - Region: Choose closest to you
   - Image: Ubuntu 22.04

3. **Setup (same as Oracle Cloud)**
   - SSH into server
   - Clone your repo
   - Install dependencies
   - Setup systemd service

### Pros:
- **Very cheap**
- **Reliable**
- **Easy to manage**
- **Good documentation**

### Cons:
- **$4/month cost**
- **Credit card required**

---

## 4. Run on Your Own Hardware (Free)

**Best for: If you have an old computer**

### Requirements:
- Old laptop or desktop
- Can stay on 24/7
- Internet connection

### Setup:

1. **Install Ubuntu Server** on the old machine
2. **Follow same setup as Oracle Cloud**
3. **Use ngrok or dynamic DNS** to expose it

### Pros:
- **100% free**
- **Your own hardware**
- **Full control**

### Cons:
- **Electricity costs**
- **Hardware failure risk**
- **Requires spare computer**

---

## Comparison Table

| Option | Cost | Difficulty | Always-on | ML Support | Best For |
|--------|------|------------|-----------|------------|----------|
| **Ngrok** | Free | Easy | ❌ No | ✅ Yes | Testing/Demos |
| **Oracle Cloud** | Free | Medium | ✅ Yes | ✅ Yes | Production |
| **DigitalOcean** | $4/mo | Medium | ✅ Yes | ✅ Yes | Production |
| **Own Hardware** | Free | Hard | ✅ Yes | ✅ Yes | Hobbyists |
| **Railway** | $5 credit | Easy | ✅ Yes | ✅ Yes | Easy start |

---

## My Recommendation for You:

### Start with Ngrok (Free)
- Test your deployment locally
- No upfront cost
- Immediate results

### Then Move to Oracle Cloud (Free)
- Truly free server
- Always-on
- Production-ready

### If You Can Afford $4/month
- DigitalOcean is easiest and most reliable
- Great documentation
- Good performance

---

## Quick Start - Ngrok (Do This Now)

```bash
# Terminal 1: Start your app
cd /Users/test/fraud-detection-engine./backend
python3.12 -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Expose with ngrok
ngrok http 8000
```

Copy the ngrok URL and update your frontend to use it. Done! Your app is now live for free.
