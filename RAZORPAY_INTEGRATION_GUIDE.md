# Complete Razorpay Integration Guide

This guide will walk you through setting up Razorpay from scratch and integrating it with your application.

## 🚀 Step 1: Create Razorpay Account

### 1.1 Sign Up for Razorpay
1. Go to [https://razorpay.com](https://razorpay.com)
2. Click "Sign Up" 
3. Choose "Business Account"
4. Fill in your business details:
   - Business Name
   - Business Type
   - Contact Information
   - Bank Account Details

### 1.2 Complete KYC Verification
1. Upload required documents:
   - PAN Card
   - Business Registration Certificate
   - Bank Account Details
   - Address Proof
2. Wait for verification (usually 24-48 hours)

## 🔑 Step 2: Get Razorpay Credentials

### 2.1 Access Dashboard
1. Login to [Razorpay Dashboard](https://dashboard.razorpay.com)
2. Go to "Settings" → "API Keys"

### 2.2 Generate API Keys
1. **Test Mode** (for development):
   - Click "Generate Test Key"
   - Copy `Key ID` and `Key Secret`
   - Example: `rzp_test_xxxxxxxxxxxxx`

2. **Live Mode** (for production):
   - Complete KYC first
   - Click "Generate Live Key"
   - Copy `Key ID` and `Key Secret`
   - Example: `rzp_live_xxxxxxxxxxxxx`

### 2.3 Get Webhook Secret
1. Go to "Settings" → "Webhooks"
2. Click "Add New Webhook"
3. Set webhook URL: `https://yourdomain.com/payments/webhook`
4. Select events: `payment.captured`, `payment.failed`
5. Copy the webhook secret (starts with `whsec_`)

## ⚙️ Step 3: Configure Environment Variables

### 3.1 Create .env File
Create a `.env` file in your project root:

```bash
# Razorpay Configuration
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
RAZORPAY_SECRET=your_test_secret_key
RAZORPAY_BASE_URL=https://api.razorpay.com/v1

# Webhook Configuration
RAZORPAY_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx

# For Production (after KYC approval)
# RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxx
# RAZORPAY_SECRET=your_live_secret_key
```

### 3.2 Set Environment Variables

#### Windows (PowerShell):
```powershell
$env:RAZORPAY_KEY_ID="rzp_test_xxxxxxxxxxxxx"
$env:RAZORPAY_SECRET="your_test_secret_key"
$env:RAZORPAY_WEBHOOK_SECRET="whsec_xxxxxxxxxxxxx"
```

#### Windows (Command Prompt):
```cmd
set RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
set RAZORPAY_SECRET=your_test_secret_key
set RAZORPAY_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
```

#### Linux/Mac:
```bash
export RAZORPAY_KEY_ID="rzp_test_xxxxxxxxxxxxx"
export RAZORPAY_SECRET="your_test_secret_key"
export RAZORPAY_WEBHOOK_SECRET="whsec_xxxxxxxxxxxxx"
```

## 🧪 Step 4: Test Configuration

### 4.1 Test Script
Create a test file `test_razorpay_config.py`:

```python
import os
from payment.razorpay_client import RazorpayClient

def test_configuration():
    print("🔧 Testing Razorpay Configuration")
    print("=" * 40)
    
    # Check environment variables
    key_id = os.getenv('RAZORPAY_KEY_ID')
    secret = os.getenv('RAZORPAY_SECRET')
    webhook_secret = os.getenv('RAZORPAY_WEBHOOK_SECRET')
    
    print(f"Key ID: {'✅ Set' if key_id and key_id != 'rzp_test_123456789' else '❌ Not set'}")
    print(f"Secret: {'✅ Set' if secret and secret != 'test_secret_123456789' else '❌ Not set'}")
    print(f"Webhook Secret: {'✅ Set' if webhook_secret and webhook_secret != 'your_razorpay_webhook_secret' else '❌ Not set'}")
    
    if not key_id or not secret:
        print("\n❌ Configuration incomplete!")
        print("Please set RAZORPAY_KEY_ID and RAZORPAY_SECRET environment variables")
        return False
    
    try:
        # Test Razorpay client
        client = RazorpayClient()
        print("\n✅ Razorpay client initialized successfully")
        
        # Test payment link creation
        response = client.create_payment_link(
            amount=1.0,
            description="Test payment",
            customer_name="Test User",
            customer_email="test@example.com"
        )
        
        if "error" in response:
            print(f"❌ Payment link creation failed: {response['error']}")
            return False
        else:
            print(f"✅ Payment link created: {response.get('id')}")
            print(f"Payment URL: {response.get('short_url')}")
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    test_configuration()
```

### 4.2 Run Test
```bash
python test_razorpay_config.py
```

## 🌐 Step 5: Set Up Webhook Endpoint

### 5.1 Configure Webhook in Razorpay Dashboard
1. Go to "Settings" → "Webhooks"
2. Add webhook URL: `https://yourdomain.com/payments/webhook`
3. Select events:
   - `payment.captured`
   - `payment.failed`
   - `payment.pending`
4. Save and copy the webhook secret

### 5.2 Test Webhook Locally (Optional)
Use ngrok to test webhooks locally:

```bash
# Install ngrok
npm install -g ngrok

# Expose your local server
ngrok http 8000

# Use the ngrok URL in Razorpay webhook settings
# Example: https://abc123.ngrok.io/payments/webhook
```

## 🚀 Step 6: Test Payment Flow

### 6.1 Test Payment Creation
```bash
# Test mock payment
curl -X POST "http://localhost:8000/payments/create" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100.0,
    "currency": "INR",
    "customer_name": "Test User",
    "customer_email": "test@example.com"
  }'
```

### 6.2 Test Live Payment
```bash
# Test live payment (requires valid credentials)
curl -X POST "http://localhost:8000/payments/create-live" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 100.0,
    "currency": "INR",
    "customer_name": "Test User",
    "customer_email": "test@example.com"
  }'
```

### 6.3 Test Diagnostics
```bash
curl -X GET "http://localhost:8000/payments/diagnostics"
```

## 🔧 Step 7: Integration with Your App

### 7.1 Update Your Main App
In your `app.py` or main application file:

```python
from fastapi import FastAPI
from payment.controller import router as payment_router

app = FastAPI()

# Include payment routes
app.include_router(payment_router, prefix="/payments", tags=["payments"])

# Your other routes...
```

### 7.2 Update Existing Code
Replace old payment imports with new ones:

```python
# OLD
from services.payment_service import create_payment_link
from utils.razorpay_utils import create_razorpay_payment_link

# NEW
from payment import PaymentService, RazorpayClient

# Usage
payment_service = PaymentService(db)
payment = payment_service.create_payment_link(payload, mock=False)
```

## 🐛 Troubleshooting

### Common Issues

#### 1. "Configuration Error"
```
Error: RAZORPAY_KEY_ID not configured properly
```
**Solution**: Set proper environment variables

#### 2. "API Error 401"
```
Error: Razorpay API error: 401 - Unauthorized
```
**Solution**: Check if Key ID and Secret are correct

#### 3. "Webhook Signature Mismatch"
```
Error: Signature validation failed
```
**Solution**: Verify webhook secret matches Razorpay dashboard

#### 4. "Payment Link Creation Failed"
```
Error: Razorpay API error: 400 - Bad Request
```
**Solution**: Check amount (must be > 0) and currency

### Debug Steps

1. **Check Environment Variables**:
```bash
python -c "import os; print('RAZORPAY_KEY_ID:', os.getenv('RAZORPAY_KEY_ID'))"
```

2. **Test Configuration**:
```bash
python test_razorpay_config.py
```

3. **Check Diagnostics**:
```bash
curl -X GET "http://localhost:8000/payments/diagnostics"
```

4. **Check Logs**: Look for `[RAZORPAY_CLIENT]` and `[PAYMENT_SERVICE]` logs

## 📋 Production Checklist

### Before Going Live:
- [ ] Complete Razorpay KYC verification
- [ ] Switch to live API keys
- [ ] Set up production webhook URL
- [ ] Test payment flow end-to-end
- [ ] Set up monitoring and alerts
- [ ] Configure proper error handling
- [ ] Test webhook processing
- [ ] Verify order status updates

### Environment Variables for Production:
```bash
RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxx
RAZORPAY_SECRET=your_live_secret_key
RAZORPAY_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
RAZORPAY_BASE_URL=https://api.razorpay.com/v1
```

## 🆘 Getting Help

### Razorpay Support:
- **Documentation**: [https://razorpay.com/docs](https://razorpay.com/docs)
- **Support**: [https://razorpay.com/support](https://razorpay.com/support)
- **Community**: [https://github.com/razorpay](https://github.com/razorpay)

### Your Application:
- Check logs for detailed error messages
- Use diagnostics endpoint to verify configuration
- Test with mock payments first
- Verify webhook processing

---

**Next Steps**: Follow this guide step by step, and you'll have Razorpay fully integrated! 🎉
