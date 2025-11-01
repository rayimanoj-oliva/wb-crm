#!/bin/bash

# Test curl command for Lead Appointment Flow starting point messages
# This simulates a WhatsApp webhook payload when a customer clicks a link

# Test URL - Update with your actual server URL
BASE_URL="http://localhost:8000"
# BASE_URL="https://your-production-server.com"

# Example 1: Hair Regrowth treatments
curl -X POST "${BASE_URL}/ws/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [
      {
        "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
        "changes": [
          {
            "value": {
              "messaging_product": "whatsapp",
              "metadata": {
                "display_phone_number": "917729992376",
                "phone_number_id": "367633743092037"
              },
              "contacts": [
                {
                  "profile": {
                    "name": "Test User"
                  },
                  "wa_id": "919876543210"
                }
              ],
              "messages": [
                {
                  "from": "919876543210",
                  "id": "wamid.test123456789",
                  "timestamp": "'$(date +%s)'",
                  "type": "text",
                  "text": {
                    "body": "Hi! I saw your ad for Oliva'\''s Hair Regrowth treatments and want to know more."
                  }
                }
              ]
            },
            "field": "messages"
          }
        ]
      }
    ]
  }'

echo ""
echo "---"
echo ""

# Example 2: Precision+ Laser Hair Reduction
curl -X POST "${BASE_URL}/ws/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [
      {
        "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
        "changes": [
          {
            "value": {
              "messaging_product": "whatsapp",
              "metadata": {
                "display_phone_number": "917729992376",
                "phone_number_id": "367633743092037"
              },
              "contacts": [
                {
                  "profile": {
                    "name": "Test User"
                  },
                  "wa_id": "919876543211"
                }
              ],
              "messages": [
                {
                  "from": "919876543211",
                  "id": "wamid.test123456790",
                  "timestamp": "'$(date +%s)'",
                  "type": "text",
                  "text": {
                    "body": "Hi! I saw your ad for Oliva'\''s Precision+ Laser Hair Reduction and want to know more."
                  }
                }
              ]
            },
            "field": "messages"
          }
        ]
      }
    ]
  }'

