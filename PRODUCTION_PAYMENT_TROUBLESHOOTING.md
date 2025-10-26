# Production Payment Troubleshooting Guide

## 🔍 Problem: Payment Links Not Being Sent to Customers in Production

### Symptoms:
- ✅ Works in local environment
- ❌ Does not work in production
- ❌ Customers not receiving payment links via WhatsApp

## 🛠️ Step-by-Step Troubleshooting

### Step 1: Run Diagnostics Script

```bash
python test_production_payment.py
```

This will test:
- Environment variables
- Razorpay API connection
- WhatsApp API connection
- Payment service
- Cart checkout service

### Step 2: Check Environment Variables

**Verify these environment variables are set in production:**

```bash
# Check if variables are set
echo $RAZORPAY_KEY_ID
echo $RAZORPAY_SECRET
echo $WHATSAPP_PHONE_ID
echo $WHATSAPP_TOKEN
```

**Common Issues:**
1. Environment variables not loaded
2. Wrong variable names
3. Extra spaces or quotes
4. Missing .env file in production

**Solution:**
```bash
# In production, set environment variables
export RAZORPAY_KEY_ID="rzp_test_xxxxxxxxxxxxx"
export RAZORPAY_SECRET="your_secret_key"
export WHATSAPP_PHONE_ID="367633743092037"
export WHATSAPP_TOKEN="your_token"

# Or add to .env file
# Make sure .env is loaded by your application
```

### Step 3: Check Razorpay Configuration

**Test Razorpay API directly:**

```bash
curl -X POST https://api.razorpay.com/v1/payment_links \
  -u "rzp_test_xxxxx:your_secret" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 10000,
    "currency": "INR",
    "description": "Test payment"
  }'
```

**Expected Response:**
```json
{
  "id": "plink_xxxxx",
  "short_url": "https://rzp.io/i/xxxxx",
  "status": "created"
}
```

**Common Issues:**
1. Invalid credentials
2. Wrong environment (test vs live keys)
3. Network firewall blocking Razorpay API
4. Razorpay account suspended

### Step 4: Check WhatsApp Configuration

**Verify WhatsApp token is working:**

```bash
# Check database for active token
python -c "
from database.db import SessionLocal
from services.whatsapp_service import get_latest_token
db = SessionLocal()
token = get_latest_token(db)
print('Token:', token.token if token else 'No token')
db.close()
"
```

**Common Issues:**
1. WhatsApp token expired
2. Token not in database
3. Invalid phone number ID
4. WhatsApp API rate limit

### Step 5: Check Application Logs

**Look for error messages in logs:**

```bash
# Check for payment-related errors
grep -i "payment" /var/log/your-app.log
grep -i "razorpay" /var/log/your-app.log
grep -i "error" /var/log/your-app.log
```

**Common Error Patterns:**
- `ConfigurationError: RAZORPAY_KEY_ID not configured`
- `APIError: Razorpay API error: 401 Unauthorized`
- `ConnectionError: Unable to connect to payment service`
- `TokenError: WhatsApp token not found`

### Step 6: Test Payment Flow Manually

**Create a test payment:**

```python
from services.cart_checkout_service import CartCheckoutService
from database.db import SessionLocal

db = SessionLocal()
checkout_service = CartCheckoutService(db)

result = await checkout_service.generate_payment_link_for_order(
    order_id="test_order_123",
    customer_wa_id="918309866859",  # Your test number
    customer_name="Test User",
    customer_email="test@example.com"
)

print(result)
```

## 🔧 Common Fixes

### Fix 1: Environment Variables Not Loaded

**Problem:** Environment variables not available to application

**Solution:**
```bash
# Option 1: Use systemd service file
[Service]
Environment="RAZORPAY_KEY_ID=rzp_test_xxxxx"
Environment="RAZORPAY_SECRET=your_secret"

# Option 2: Load from .env file
# Make sure .env is in correct location
# Add python-dotenv to load .env
```

### Fix 2: Wrong Razorpay Credentials

**Problem:** Using test credentials in production

**Solution:**
```bash
# Verify which environment
if [[ $RAZORPAY_KEY_ID == *"_test_"* ]]; then
  echo "Using test credentials"
else
  echo "Using live credentials"
fi

# For production, use live credentials after KYC
export RAZORPAY_KEY_ID="rzp_live_xxxxx"
export RAZORPAY_SECRET="live_secret"
```

### Fix 3: Network/Firewall Issues

**Problem:** Can't reach Razorpay API

**Solution:**
```bash
# Test connectivity
curl -v https://api.razorpay.com/v1/payment_links

# Check firewall rules
sudo ufw status
sudo iptables -L

# Add exception if needed
sudo ufw allow out https
```

### Fix 4: WhatsApp Token Expired

**Problem:** WhatsApp token has expired

**Solution:**
```python
# Update WhatsApp token in database
from database.db import SessionLocal
from models.models import WhatsAppToken
from datetime import datetime, timedelta

db = SessionLocal()
token_entry = db.query(WhatsAppToken).first()
if token_entry:
    token_entry.token = "new_token_here"
    token_entry.expires_at = datetime.utcnow() + timedelta(days=60)
    db.commit()
```

### Fix 5: Database Connection Issues

**Problem:** Can't connect to database

**Solution:**
```bash
# Test database connection
python -c "
from database.db import SessionLocal
try:
    db = SessionLocal()
    db.execute('SELECT 1')
    print('Database connected')
    db.close()
except Exception as e:
    print(f'Database error: {e}')
"
```

## 📊 Monitoring & Logging

### Add Logging to Payment Flow

```python
import logging

# Set up logger
logger = logging.getLogger(__name__)

# In payment generation
try:
    logger.info(f"Creating payment for order {order_id}")
    payment = create_payment_link(...)
    logger.info(f"Payment created: {payment.razorpay_id}")
except Exception as e:
    logger.error(f"Payment creation failed: {e}", exc_info=True)
```

### Check Payment Status

```sql
-- Check recent payments
SELECT * FROM payments 
ORDER BY created_at DESC 
LIMIT 10;

-- Check for failed payments
SELECT * FROM payments 
WHERE status = 'failed' 
ORDER BY created_at DESC;
```

## 🚨 Emergency Fix: Bypass Issue

**If payment links aren't working:**

1. **Manual Fallback:** Send payment link via admin panel
2. **Alternative Payment Method:** Use different payment gateway
3. **Direct Payment Link:** Generate link manually via Razorpay dashboard

## 📝 Checklist

Before reporting issue, verify:

- [ ] Environment variables set correctly
- [ ] Razorpay credentials valid
- [ ] WhatsApp token active
- [ ] Database connected
- [ ] Network connectivity to Razorpay
- [ ] Application logs checked
- [ ] Test payment created successfully
- [ ] Error messages captured

## 🆘 Getting Help

If issue persists:

1. Run diagnostic script: `python test_production_payment.py`
2. Collect logs: `tail -n 100 /var/log/your-app.log > error.log`
3. Capture environment: `env | grep -E "(RAZORPAY|WHATSAPP)" > env.txt`
4. Create test case with specific order ID that fails
5. Contact support with all collected information

## 🔄 Quick Reset

**Complete reset procedure:**

```bash
# 1. Restart application
sudo systemctl restart your-app

# 2. Clear cache
redis-cli FLUSHALL

# 3. Test health endpoint
curl http://localhost:8000/health

# 4. Run diagnostics
python test_production_payment.py

# 5. Test payment creation
python -c "
from payment.razorpay_client import RazorpayClient
client = RazorpayClient()
result = client.create_payment_link(amount=1.0, description='Test')
print(result)
"
```

## 📚 Additional Resources

- Razorpay API Docs: https://razorpay.com/docs/
- WhatsApp Business API: https://developers.facebook.com/docs/whatsapp
- Payment Troubleshooting Guide: `PAYMENT_VERIFICATION_GUIDE.md`

---

**Remember:** Always test in staging before applying to production!
