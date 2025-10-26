# Payment Module

A comprehensive payment processing module for handling Razorpay integration, cart checkout, and payment operations.

## 📁 Structure

```
payment/
├── __init__.py                 # Module initialization and exports
├── razorpay_client.py         # Razorpay API client
├── payment_service.py         # Core payment processing service
├── cart_checkout_service.py   # Cart checkout operations
├── schemas.py                 # Pydantic models and validation
├── exceptions.py             # Custom exception classes
├── controller.py             # FastAPI endpoints
└── README.md                 # This file
```

## 🚀 Features

### Core Components

1. **RazorpayClient** (`razorpay_client.py`)
   - Direct Razorpay API integration
   - Payment link creation
   - Payment status tracking
   - Webhook signature validation
   - Configuration validation

2. **PaymentService** (`payment_service.py`)
   - Payment creation and management
   - Database operations
   - Fallback to proxy API
   - Shopify integration
   - System diagnostics

3. **CartCheckoutService** (`cart_checkout_service.py`)
   - Order total calculation
   - Payment link generation for orders
   - WhatsApp notifications
   - Interactive payment buttons
   - Order summary formatting

4. **Schemas** (`schemas.py`)
   - Request/response models
   - Data validation
   - Type safety
   - Enum definitions

5. **Exceptions** (`exceptions.py`)
   - Custom exception hierarchy
   - Specific error types
   - Error context preservation

6. **Controller** (`controller.py`)
   - REST API endpoints
   - Webhook handling
   - Payment diagnostics
   - Error handling

## 📋 API Endpoints

### Payment Operations
- `POST /payments/create` - Create mock payment link
- `POST /payments/create-live` - Create live payment link
- `POST /payments/create-link` - Create payment link for order
- `POST /payments/webhook` - Handle Razorpay webhooks
- `GET /payments/diagnostics` - System diagnostics

### Request/Response Models

#### PaymentCreate
```python
{
    "order_id": "string",
    "amount": 100.0,
    "currency": "INR",
    "payment_method": "upi",
    "customer_name": "John Doe",
    "customer_email": "john@example.com",
    "customer_phone": "+1234567890"
}
```

#### PaymentResponse
```python
{
    "payment_id": "string",
    "razorpay_id": "string", 
    "payment_url": "string",
    "status": "created",
    "amount": 100.0,
    "currency": "INR",
    "order_id": "string",
    "created_at": "2024-01-01T00:00:00Z",
    "notification_sent": true
}
```

## 🔧 Configuration

### Environment Variables

```bash
# Razorpay Configuration
RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxx
RAZORPAY_SECRET=your_live_secret_key
RAZORPAY_BASE_URL=https://api.razorpay.com/v1

# Proxy Configuration (Fallback)
RAZORPAY_USERNAME=your_username
RAZORPAY_PASSWORD=your_password
RAZORPAY_TOKEN_URL=https://payments.olivaclinic.com/api/token
RAZORPAY_PAYMENT_URL=https://payments.olivaclinic.com/api/payment

# Webhook Configuration
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret

# Shopify Configuration
SHOPIFY_STORE=your-store
SHOPIFY_API_KEY=your_api_key
SHOPIFY_PASSWORD=your_password
```

## 🛠️ Usage Examples

### Basic Payment Creation

```python
from payment import PaymentService, PaymentCreate

# Initialize service
payment_service = PaymentService(db)

# Create payment
payment_data = PaymentCreate(
    order_id="ORDER_123",
    amount=100.0,
    currency="INR",
    customer_name="John Doe",
    customer_email="john@example.com"
)

payment = payment_service.create_payment_link(payment_data, mock=False)
print(f"Payment URL: {payment.razorpay_short_url}")
```

### Cart Checkout

```python
from payment import CartCheckoutService

# Initialize service
cart_service = CartCheckoutService(db)

# Generate payment link for order
result = await cart_service.generate_payment_link_for_order(
    order_id="ORDER_123",
    customer_wa_id="918309866859",
    customer_name="John Doe"
)

if result["success"]:
    print(f"Payment URL: {result['payment_url']}")
else:
    print(f"Error: {result['error']}")
```

### Razorpay Client Usage

```python
from payment import RazorpayClient

# Initialize client
client = RazorpayClient()

# Create payment link
response = client.create_payment_link(
    amount=100.0,
    description="Test payment",
    customer_name="John Doe",
    customer_email="john@example.com"
)

print(f"Payment ID: {response['id']}")
print(f"Payment URL: {response['short_url']}")
```

## 🔍 Error Handling

### Exception Hierarchy

```python
PaymentError (Base)
├── RazorpayError
├── ConfigurationError
├── ValidationError
├── OrderNotFoundError
├── PaymentNotFoundError
├── PaymentExpiredError
├── PaymentAlreadyProcessedError
├── InsufficientFundsError
├── PaymentGatewayError
├── NotificationError
├── WebhookError
│   └── SignatureValidationError
├── TimeoutError
└── ConnectionError
```

### Error Response Format

```python
{
    "error": "Error message",
    "error_type": "error_category",
    "details": {
        "field": "additional_info"
    }
}
```

## 🧪 Testing

### Diagnostics Endpoint

Check system configuration and connectivity:

```bash
curl -X GET "http://localhost:8000/payments/diagnostics"
```

Response:
```json
{
    "razorpay_config": {
        "key_id_configured": true,
        "secret_configured": true,
        "base_url": "https://api.razorpay.com/v1",
        "key_id_prefix": "rzp_live..."
    },
    "environment": {
        "razorpay_username": true,
        "razorpay_password": true,
        "proxy_token_url": "https://payments.olivaclinic.com/api/token",
        "proxy_payment_url": "https://payments.olivaclinic.com/api/payment"
    },
    "api_test": {
        "status": "success",
        "payment_id": "plink_xxxxxxxxxxxxx"
    }
}
```

## 🔄 Integration

### With Existing Codebase

1. **Update Imports**: Replace existing payment imports with new module
2. **Update Controllers**: Use new payment controller endpoints
3. **Update Services**: Use new payment service classes
4. **Update Schemas**: Use new Pydantic models

### Migration Steps

1. **Backup**: Backup existing payment-related files
2. **Deploy**: Deploy new payment module
3. **Test**: Test payment flow with diagnostics endpoint
4. **Update**: Update imports in existing code
5. **Verify**: Verify payment operations work correctly

## 📊 Monitoring

### Logs

The module provides comprehensive logging:

- `[RAZORPAY_CLIENT]` - API client operations
- `[PAYMENT_SERVICE]` - Payment service operations  
- `[CART_CHECKOUT]` - Cart checkout operations
- `[PAYMENT_WEBHOOK]` - Webhook processing

### Metrics

Track key metrics:
- Payment success rate
- API response times
- Error rates by type
- Webhook processing time

## 🔒 Security

### Webhook Security
- Signature validation
- Timestamp verification
- Rate limiting
- IP whitelisting

### Data Protection
- Sensitive data encryption
- Secure credential storage
- Audit logging
- PCI compliance considerations

## 🚀 Deployment

### Production Checklist

- [ ] Set proper Razorpay credentials
- [ ] Configure webhook endpoints
- [ ] Test payment flow
- [ ] Monitor error rates
- [ ] Set up alerts
- [ ] Backup configuration

### Environment Setup

```bash
# Production environment
export RAZORPAY_KEY_ID="rzp_live_xxxxxxxxxxxxx"
export RAZORPAY_SECRET="your_live_secret_key"
export RAZORPAY_WEBHOOK_SECRET="your_webhook_secret"

# Test environment  
export RAZORPAY_KEY_ID="rzp_test_xxxxxxxxxxxxx"
export RAZORPAY_SECRET="your_test_secret_key"
```

## 📞 Support

For issues or questions:
1. Check diagnostics endpoint
2. Review logs for error details
3. Verify configuration
4. Test with mock payments first
5. Contact development team

---

**Version**: 1.0.0  
**Last Updated**: 2024-01-01  
**Maintainer**: Development Team
