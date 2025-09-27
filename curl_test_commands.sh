#!/bin/bash
# Curl commands for testing prefill messages with referrer tracking

echo "🧪 Curl Commands for Testing Prefill Messages"
echo "=============================================="

echo ""
echo "1️⃣ Test webhook with Banjara Hills referrer:"
echo "--------------------------------------------"
curl -X POST "http://127.0.0.1:8000/ws/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "contacts": [{
            "wa_id": "918309867004",
            "profile": {"name": "Banjara Hills User"}
          }],
          "messages": [{
            "from": "918309867004",
            "id": "banjara_test_123",
            "timestamp": "1758972000",
            "type": "text",
            "text": {"body": "Hi, I want to book an appointment. I came from banjara.olivaclinics.com"}
          }],
          "metadata": {"display_phone_number": "917729992376"}
        }
      }]
    }]
  }'

echo ""
echo "2️⃣ Test webhook with Jubilee Hills referrer:"
echo "---------------------------------------------"
curl -X POST "http://127.0.0.1:8000/ws/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "contacts": [{
            "wa_id": "918309867005",
            "profile": {"name": "Jubilee Hills User"}
          }],
          "messages": [{
            "from": "918309867005",
            "id": "jubilee_test_123",
            "timestamp": "1758972000",
            "type": "text",
            "text": {"body": "Hello, I need to book an appointment at Jubilee Hills center"}
          }],
          "metadata": {"display_phone_number": "917729992376"}
        }
      }]
    }]
  }'

echo ""
echo "3️⃣ Test webhook with UTM parameters:"
echo "-------------------------------------"
curl -X POST "http://127.0.0.1:8000/ws/webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "contacts": [{
            "wa_id": "918309867006",
            "profile": {"name": "UTM Test User"}
          }],
          "messages": [{
            "from": "918309867006",
            "id": "utm_test_123",
            "timestamp": "1758972000",
            "type": "text",
            "text": {"body": "utm_source=olivaclinics&utm_medium=website&utm_campaign=gachibowli&utm_content=hyderabad"}
          }],
          "metadata": {"display_phone_number": "917729992376"}
        }
      }]
    }]
  }'

echo ""
echo "4️⃣ Check referrer tracking for Banjara Hills:"
echo "----------------------------------------------"
curl -X GET "http://127.0.0.1:8000/referrer/918309867004" \
  -H "accept: application/json"

echo ""
echo "5️⃣ Check referrer tracking for Jubilee Hills:"
echo "----------------------------------------------"
curl -X GET "http://127.0.0.1:8000/referrer/918309867005" \
  -H "accept: application/json"

echo ""
echo "6️⃣ Check referrer tracking for UTM test:"
echo "-----------------------------------------"
curl -X GET "http://127.0.0.1:8000/referrer/918309867006" \
  -H "accept: application/json"

echo ""
echo "7️⃣ Get all referrer records:"
echo "----------------------------"
curl -X GET "http://127.0.0.1:8000/referrer/" \
  -H "accept: application/json"

echo ""
echo "✅ Curl testing completed!"
echo ""
echo "📋 Expected Results:"
echo "- Referrer tracking records should be created"
echo "- Center names should be captured correctly"
echo "- UTM parameters should be stored"
echo "- Appointment confirmations should include center info"
