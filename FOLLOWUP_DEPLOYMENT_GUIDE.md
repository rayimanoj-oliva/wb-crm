# Follow-Up Scheduler Deployment Guide

## 📋 Quick Start Checklist

- [ ] Install Redis on production server
- [ ] Configure Redis environment variables
- [ ] Restart the FastAPI application
- [ ] Verify scheduler is running
- [ ] Monitor logs for any issues

---

## Step 1: Install Redis on Production Server

### For Ubuntu/Debian (EC2):

```bash
# SSH into your EC2 instance
ssh ubuntu@your-ec2-ip

# Update package list
sudo apt-get update

# Install Redis
sudo apt-get install redis-server -y

# Start Redis service
sudo systemctl start redis-server

# Enable Redis to start on boot
sudo systemctl enable redis-server

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

### For Amazon Linux:

```bash
sudo yum install redis -y
sudo systemctl start redis
sudo systemctl enable redis
redis-cli ping
```

---

## Step 2: Configure Environment Variables

### Option A: Add to your `.env` file (if you use one):

```bash
# Add these lines to your .env file
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
# REDIS_PASSWORD=your_password_if_set  # Only if Redis has password
```

### Option B: Set system environment variables:

```bash
# Add to ~/.bashrc or ~/.profile
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0

# Reload
source ~/.bashrc
```

### Option C: Add to systemd service file (if using systemd):

Edit your service file (e.g., `/etc/systemd/system/wb-crm.service`):

```ini
[Service]
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
Environment="REDIS_DB=0"
```

---

## Step 3: Update Your Application Deployment

### If using manual restart (your current setup):

```bash
# SSH into EC2
ssh ubuntu@your-ec2-ip

# Navigate to your project
cd wb-crm

# Pull latest code (if using Git)
git pull origin main

# Restart the application
pkill -f uvicorn
nohup uvicorn app:app --host 0.0.0.0 --port 8001 > logs.out 2>&1 &
```

### Better: Use systemd service (Recommended):

Create `/etc/systemd/system/wb-crm.service`:

```ini
[Unit]
Description=WB CRM FastAPI Application
After=network.target redis-server.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/wb-crm
Environment="PATH=/home/ubuntu/myenv/bin"
Environment="REDIS_HOST=localhost"
Environment="REDIS_PORT=6379"
Environment="REDIS_DB=0"
ExecStart=/home/ubuntu/myenv/bin/uvicorn app:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable wb-crm
sudo systemctl start wb-crm
sudo systemctl status wb-crm
```

---

## Step 4: Verify Setup

### 4.1 Check Redis Connection

```bash
# Test Redis directly
redis-cli ping

# Check if Redis is listening
sudo netstat -tlnp | grep 6379
```

### 4.2 Check Application Logs

```bash
# If using nohup
tail -f logs.out

# If using systemd
sudo journalctl -u wb-crm -f

# Look for these messages:
# [Redis] Successfully connected to Redis at localhost:6379
# [followup_scheduler] INFO - Starting follow-up scheduler background task
```

### 4.3 Test the Scheduler

Wait 30-60 seconds and check logs for:

```
[followup_scheduler] INFO - Starting iteration 1
[followup_scheduler] INFO - Found X customer(s) due for follow-up
```

---

## Step 5: Monitor and Debug

### Check if scheduler is running:

```bash
# Check if uvicorn process is running
ps aux | grep uvicorn

# Check Redis connection from Python
python3 -c "from cache.redis_connection import get_redis_client; client = get_redis_client(); print('Redis OK' if client else 'Redis FAILED')"
```

### Common Issues:

#### Issue 1: "Redis WARNING - Could not connect to Redis"
**Solution**: Check if Redis is running:
```bash
sudo systemctl status redis-server
sudo systemctl start redis-server
```

#### Issue 2: Scheduler not starting
**Solution**: Check application logs for errors. Make sure the startup event is executing.

#### Issue 3: Duplicate messages (if multiple instances)
**Solution**: Ensure Redis is accessible to all instances and check distributed locks are working.

---

## Step 6: Optional - Production Redis Setup

For better reliability in production, consider:

### Using Redis with Authentication:

1. Set Redis password:
```bash
sudo nano /etc/redis/redis.conf
# Uncomment: requirepass your_strong_password
sudo systemctl restart redis-server
```

2. Update environment:
```bash
export REDIS_PASSWORD=your_strong_password
```

### Using Remote Redis (AWS ElastiCache, Redis Cloud, etc.):

```bash
export REDIS_HOST=your-redis-endpoint.cache.amazonaws.com
export REDIS_PORT=6379
export REDIS_PASSWORD=your-password
# OR use Redis URL
export REDIS_URL=redis://:password@host:port/db
```

---

## Testing Checklist

After deployment, verify:

- [ ] Redis is running: `redis-cli ping` returns `PONG`
- [ ] Application logs show: `[Redis] Successfully connected to Redis`
- [ ] Scheduler logs show: `[followup_scheduler] INFO - Starting iteration`
- [ ] No error messages about Redis connection
- [ ] Follow-up messages are being sent to customers
- [ ] No duplicate messages are sent (if multiple instances)

---

## Quick Verification Script

Create `test_followup_setup.py`:

```python
#!/usr/bin/env python3
"""Quick test script to verify follow-up setup"""

from cache.redis_connection import get_redis_client
from services.followup_service import acquire_followup_lock, release_followup_lock

print("🔍 Testing Follow-Up Setup...")
print("=" * 50)

# Test Redis
redis_client = get_redis_client()
if redis_client:
    print("✅ Redis: Connected successfully")
    try:
        redis_client.ping()
        print("✅ Redis: Ping successful")
    except Exception as e:
        print(f"❌ Redis: Ping failed - {e}")
else:
    print("❌ Redis: NOT connected (will work without distributed locking)")

# Test Locking
print("\n🔒 Testing Distributed Locking...")
lock_value = acquire_followup_lock("test-customer-123")
if lock_value:
    print("✅ Lock: Acquired successfully")
    release_followup_lock("test-customer-123", lock_value)
    print("✅ Lock: Released successfully")
else:
    print("❌ Lock: Failed to acquire")

print("\n" + "=" * 50)
print("✅ Setup verification complete!")
```

Run it:
```bash
source ~/myenv/bin/activate
cd wb-crm
python test_followup_setup.py
```

---

## Need Help?

If you encounter issues:

1. Check application logs: `tail -f logs.out` or `sudo journalctl -u wb-crm -f`
2. Check Redis logs: `sudo journalctl -u redis-server -f`
3. Verify environment variables are set correctly
4. Ensure Redis is accessible from your application

---

## Summary

✅ **Required**: Redis server running on production  
✅ **Recommended**: Configure Redis via environment variables  
✅ **Best Practice**: Use systemd service for automatic restarts  
✅ **Monitoring**: Check logs regularly for scheduler activity  

Your follow-up scheduler will now:
- ✅ Work reliably in production
- ✅ Prevent duplicate messages across multiple instances
- ✅ Handle Redis failures gracefully
- ✅ Provide detailed logging for debugging

