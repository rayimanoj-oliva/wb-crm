# Payment Module Migration Guide

This guide helps you migrate from the old payment system to the new organized payment module.

## 📋 Migration Checklist

- [ ] Deploy new payment module
- [ ] Update imports in existing files
- [ ] Test payment functionality
- [ ] Update API endpoints
- [ ] Verify webhook handling
- [ ] Clean up old files

## 🔄 Import Updates

### Old Imports → New Imports

#### Payment Service
```python
# OLD
from services.payment_service import create_payment_link
from utils.razorpay_utils import create_razorpay_payment_link

# NEW
from payment import PaymentService, RazorpayClient
```

#### Cart Checkout Service
```python
# OLD
from services.cart_checkout_service import CartCheckoutService

# NEW
from payment import CartCheckoutService
```

#### Payment Schemas
```python
# OLD
from schemas.payment_schema import PaymentCreate

# NEW
from payment import PaymentCreate, PaymentResponse
```

#### Payment Controller
```python
# OLD
from controllers.payment_controller import router

# NEW
from payment.controller import router
```

## 📁 Files to Update

### 1. Controllers

#### `controllers/payment_controller.py`
```python
# Replace entire file with:
from payment.controller import router
```

#### `controllers/web_socket.py`
```python
# OLD
from utils.razorpay_utils import create_razorpay_payment_link

# NEW
from payment import RazorpayClient
```

#### `controllers/components/interactive_type.py`
```python
# OLD
from services.cart_checkout_service import CartCheckoutService

# NEW
from payment import CartCheckoutService
```

### 2. Services

#### `services/cart_checkout_service.py`
```python
# Replace entire file with:
from payment.cart_checkout_service import CartCheckoutService
```

#### `services/payment_service.py`
```python
# Replace entire file with:
from payment.payment_service import PaymentService
```

### 3. Utils

#### `utils/razorpay_utils.py`
```python
# Replace entire file with:
from payment.razorpay_client import RazorpayClient
```

## 🔧 Code Updates

### Payment Creation

#### Old Code
```python
from services.payment_service import create_payment_link
from schemas.payment_schema import PaymentCreate

payment = create_payment_link(db, payload, mock=False)
```

#### New Code
```python
from payment import PaymentService, PaymentCreate

payment_service = PaymentService(db)
payment = payment_service.create_payment_link(payload, mock=False)
```

### Cart Checkout

#### Old Code
```python
from services.cart_checkout_service import CartCheckoutService

checkout_service = CartCheckoutService(db)
result = await checkout_service.generate_payment_link_for_order(...)
```

#### New Code
```python
from payment import CartCheckoutService

checkout_service = CartCheckoutService(db)
result = await checkout_service.generate_payment_link_for_order(...)
```

### Razorpay Client

#### Old Code
```python
from utils.razorpay_utils import create_razorpay_payment_link

response = create_razorpay_payment_link(amount=100.0, description="Test")
```

#### New Code
```python
from payment import RazorpayClient

client = RazorpayClient()
response = client.create_payment_link(amount=100.0, description="Test")
```

## 🚀 Deployment Steps

### 1. Deploy New Module
```bash
# Copy payment module to production
cp -r payment/ /path/to/production/
```

### 2. Update Main App
```python
# In app.py or main.py
from payment.controller import router as payment_router
app.include_router(payment_router, prefix="/payments")
```

### 3. Test Configuration
```bash
# Test diagnostics endpoint
curl -X GET "http://localhost:8000/payments/diagnostics"
```

### 4. Update Environment Variables
```bash
# Ensure these are set
export RAZORPAY_KEY_ID="rzp_live_xxxxxxxxxxxxx"
export RAZORPAY_SECRET="your_live_secret_key"
export RAZORPAY_WEBHOOK_SECRET="your_webhook_secret"
```

## 🧪 Testing

### 1. Test Payment Creation
```python
# Test mock payment
from payment import PaymentService, PaymentCreate

payment_service = PaymentService(db)
payload = PaymentCreate(amount=100.0, currency="INR")
payment = payment_service.create_payment_link(payload, mock=True)
assert payment.razorpay_short_url is not None
```

### 2. Test Cart Checkout
```python
# Test cart checkout
from payment import CartCheckoutService

cart_service = CartCheckoutService(db)
result = await cart_service.generate_payment_link_for_order(
    order_id="test_order",
    customer_wa_id="918309866859"
)
assert result["success"] == True
```

### 3. Test Diagnostics
```bash
# Test diagnostics endpoint
curl -X GET "http://localhost:8000/payments/diagnostics" | jq
```

## 🗑️ Cleanup

### Files to Remove (After Migration)
- `utils/razorpay_utils.py` (replaced by `payment/razorpay_client.py`)
- `services/payment_service.py` (replaced by `payment/payment_service.py`)
- `services/cart_checkout_service.py` (replaced by `payment/cart_checkout_service.py`)
- `controllers/payment_controller.py` (replaced by `payment/controller.py`)
- `schemas/payment_schema.py` (replaced by `payment/schemas.py`)

### Backup Old Files
```bash
# Create backup before cleanup
mkdir -p backup/payment_migration_$(date +%Y%m%d)
cp utils/razorpay_utils.py backup/payment_migration_$(date +%Y%m%d)/
cp services/payment_service.py backup/payment_migration_$(date +%Y%m%d)/
cp services/cart_checkout_service.py backup/payment_migration_$(date +%Y%m%d)/
cp controllers/payment_controller.py backup/payment_migration_$(date +%Y%m%d)/
cp schemas/payment_schema.py backup/payment_migration_$(date +%Y%m%d)/
```

## ⚠️ Important Notes

### 1. Database Compatibility
- No database changes required
- Existing payment records remain compatible
- New features use existing tables

### 2. API Compatibility
- All existing endpoints remain functional
- New endpoints added for better organization
- Response formats unchanged

### 3. Error Handling
- Enhanced error messages
- Better error categorization
- Improved debugging capabilities

### 4. Configuration
- Same environment variables
- Enhanced validation
- Better diagnostics

## 🔍 Troubleshooting

### Common Issues

#### Import Errors
```python
# If you get import errors, check:
from payment import PaymentService  # Should work
from payment.payment_service import PaymentService  # Alternative
```

#### Configuration Errors
```bash
# Check diagnostics endpoint
curl -X GET "http://localhost:8000/payments/diagnostics"
```

#### Database Errors
```python
# Ensure database session is passed correctly
payment_service = PaymentService(db)  # db is Session object
```

### Rollback Plan

If issues occur, you can rollback:

1. **Restore Old Files**
```bash
cp backup/payment_migration_$(date +%Y%m%d)/* ./
```

2. **Revert Imports**
```python
# Change back to old imports
from services.payment_service import create_payment_link
from utils.razorpay_utils import create_razorpay_payment_link
```

3. **Restart Application**
```bash
# Restart your application
sudo systemctl restart your-app
```

## ✅ Verification

### Final Checklist
- [ ] All imports updated
- [ ] Payment creation works
- [ ] Cart checkout works
- [ ] Webhooks work
- [ ] Diagnostics endpoint works
- [ ] No errors in logs
- [ ] Old files backed up
- [ ] Team notified of changes

### Success Indicators
- ✅ Payment links generated successfully
- ✅ WhatsApp notifications sent
- ✅ Webhook processing works
- ✅ No import errors
- ✅ Diagnostics show green status

---

**Migration Complete!** 🎉

The payment system is now organized, maintainable, and ready for production use.
