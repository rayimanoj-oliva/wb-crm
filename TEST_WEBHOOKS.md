# Webhook Testing Guide

## Webhook Endpoints

### First Webhook (`/webhook`)
- **POST** `/webhook` - Receive webhook messages
- **GET** `/webhook` - Verify webhook subscription

### Second Webhook (`/webhook2`)
- **POST** `/webhook2` - Receive webhook messages
- **GET** `/webhook2` - Verify webhook subscription

---

## 1. Test Webhook Verification (GET)

### First Webhook Verification
```bash
# Test webhook verification for first number
curl -X GET "http://localhost:8000/webhook?hub.mode=subscribe&hub.verify_token=your_verify_token&hub.challenge=test_challenge_123"
```

### Second Webhook Verification
```bash
# Test webhook verification for second number
curl -X GET "http://localhost:8000/webhook2?hub.mode=subscribe&hub.verify_token=your_verify_token&hub.challenge=test_challenge_456"
```

**Note:** Replace `your_verify_token` with your actual `WHATSAPP_VERIFY_TOKEN` environment variable value.

---

## 2. Test Webhook Message Reception (POST)

### First Webhook - Standard WhatsApp Webhook Payload
```bash
curl -X POST "http://localhost:8000/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [
      {
        "changes": [
          {
            "value": {
              "metadata": {
                "display_phone_number": "918309866859",
                "phone_number_id": "367633743092037"
              },
              "contacts": [
                {
                  "profile": {
                    "name": "John Doe"
                  },
                  "wa_id": "918309866859"
                }
              ],
              "messages": [
                {
                  "from": "918309866859",
                  "id": "wamid.test123",
                  "timestamp": "1234567890",
                  "type": "text",
                  "text": {
                    "body": "Hello, this is a test message"
                  }
                }
              ]
            }
          }
        ]
      }
    ]
  }'
```

### Second Webhook - Standard WhatsApp Webhook Payload
```bash
curl -X POST "http://localhost:8000/webhook2" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [
      {
        "changes": [
          {
            "value": {
              "metadata": {
                "display_phone_number": "918328607178",
                "phone_number_id": "123456789012"
              },
              "contacts": [
                {
                  "profile": {
                    "name": "Jane Smith"
                  },
                  "wa_id": "918328607178"
                }
              ],
              "messages": [
                {
                  "from": "918328607178",
                  "id": "wamid.test456",
                  "timestamp": "1234567890",
                  "type": "text",
                  "text": {
                    "body": "Test message for webhook2"
                  }
                }
              ]
            }
          }
        ]
      }
    ]
  }'
```

---

## 3. Test Status Update (Should be Ignored)

```bash
curl -X POST "http://localhost:8000/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [
      {
        "changes": [
          {
            "value": {
              "statuses": [
                {
                  "id": "wamid.test123",
                  "status": "delivered",
                  "timestamp": "1234567890",
                  "recipient_id": "918309866859"
                }
              ]
            }
          }
        ]
      }
    ]
  }'
```

Expected response: `{"status": "ok", "message": "Status update ignored"}`

---

## 4. Test with Alternative Payload Structure

```bash
curl -X POST "http://localhost:8000/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "contacts": [
      {
        "profile": {
          "name": "Test User"
        },
        "wa_id": "918309866859"
      }
    ],
    "messages": [
      {
        "from": "918309866859",
        "id": "wamid.test789",
        "timestamp": "1234567890",
        "type": "text",
        "text": {
          "body": "Alternative payload structure test"
        }
      }
    ],
    "phone_number_id": "367633743092037"
  }'
```

---

## 5. Test Error Cases

### Invalid JSON
```bash
curl -X POST "http://localhost:8000/webhook" \
  -H "Content-Type: application/json" \
  -d 'invalid json'
```

### Missing Messages/Contacts
```bash
curl -X POST "http://localhost:8000/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [
      {
        "changes": [
          {
            "value": {
              "metadata": {
                "display_phone_number": "918309866859",
                "phone_number_id": "367633743092037"
              }
            }
          }
        ]
      }
    ]
  }'
```

---

## Expected Responses

### Successful Webhook Reception
```json
{
  "status": "ok",
  "message": "Webhook received and processed"
}
```

### Webhook Verification (GET)
Returns the challenge string as plain text (e.g., `test_challenge_123`)

### Error Response
```json
{
  "status": "error",
  "message": "Invalid webhook payload"
}
```

---

## Check Logs

After testing, check the log files in the `webhook_logs/` directory:
- `webhook_*.json` - Raw payloads for first webhook
- `webhook2_*.json` - Raw payloads for second webhook
- `webhook_*_formatted.json` - Formatted JSON logs
- `webhook2_*_formatted.json` - Formatted JSON logs

---

## Production URLs

For production, replace `http://localhost:8000` with your actual domain:
- `https://yourdomain.com/webhook`
- `https://yourdomain.com/webhook2`

