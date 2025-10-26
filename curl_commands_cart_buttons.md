# Curl Commands for Testing Cart Interactive Buttons with ₹5500 Payment

## 1. Create Cart with ₹5500 Total

```bash
curl --location 'http://127.0.0.1:8000/ws/webhook' \
--header 'accept: application/json' \
--header 'Content-Type: application/json' \
--data '{
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "917729992376",
                            "phone_number_id": "PHONE_NUMBER_ID"
                        },
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
                                "id": "wamid.cart.5500.test",
                                "from": "918309866859",
                                "timestamp": "1704067200",
                                "type": "order",
                                "order": {
                                    "catalog_id": "1093353131080785",
                                    "product_items": [
                                        {
                                            "product_retailer_id": "Premium Skincare Kit",
                                            "quantity": 2,
                                            "item_price": 1500.00,
                                            "currency": "INR"
                                        },
                                        {
                                            "product_retailer_id": "Hair Care Bundle",
                                            "quantity": 1,
                                            "item_price": 2500.00,
                                            "currency": "INR"
                                        }
                                    ]
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

## 2. Test Pay Now Button (💳 Pay ₹5500.00)

```bash
curl --location 'http://127.0.0.1:8000/ws/webhook' \
--header 'accept: application/json' \
--header 'Content-Type: application/json' \
--data '{
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "917729992376",
                            "phone_number_id": "PHONE_NUMBER_ID"
                        },
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
                                "id": "wamid.button.pay.now",
                                "from": "918309866859",
                                "timestamp": "1704067200",
                                "type": "interactive",
                                "interactive": {
                                    "type": "button_reply",
                                    "button_reply": {
                                        "id": "pay_now_button",
                                        "title": "💳 Pay ₹5500.00"
                                    }
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

## 3. Test View Payment Link Button (🔗 View Payment Link)

```bash
curl --location 'http://127.0.0.1:8000/ws/webhook' \
--header 'accept: application/json' \
--header 'Content-Type: application/json' \
--data '{
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "917729992376",
                            "phone_number_id": "PHONE_NUMBER_ID"
                        },
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
                                "id": "wamid.button.view.link",
                                "from": "918309866859",
                                "timestamp": "1704067200",
                                "type": "interactive",
                                "interactive": {
                                    "type": "button_reply",
                                    "button_reply": {
                                        "id": "view_payment_link",
                                        "title": "🔗 View Payment Link"
                                    }
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

## 4. Test Order Details Button (📋 Order Details)

```bash
curl --location 'http://127.0.0.1:8000/ws/webhook' \
--header 'accept: application/json' \
--header 'Content-Type: application/json' \
--data '{
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "917729992376",
                            "phone_number_id": "PHONE_NUMBER_ID"
                        },
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
                                "id": "wamid.button.order.details",
                                "from": "918309866859",
                                "timestamp": "1704067200",
                                "type": "interactive",
                                "interactive": {
                                    "type": "button_reply",
                                    "button_reply": {
                                        "id": "order_details",
                                        "title": "📋 Order Details"
                                    }
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

## Expected Results:

### 1. Cart Creation Response:
- Detailed cart summary with ₹5500 total
- Interactive buttons: Pay Now, View Link, Order Details
- Payment link sent separately

### 2. Pay Now Button Response:
- Payment confirmation message
- Order total: ₹5500.00
- Items count and payment instructions

### 3. View Payment Link Button Response:
- Reminder to check payment link above
- Simple confirmation message

### 4. Order Details Button Response:
- Complete order information
- Order ID, status, items count, total
- Creation timestamp

## Usage Instructions:

1. **Run Cart Creation First**: Use the first curl command to create the cart
2. **Check WhatsApp**: Verify you receive the detailed cart with buttons
3. **Test Each Button**: Use the individual curl commands to test each button
4. **Verify Responses**: Check WhatsApp for appropriate responses to each button click

## Notes:

- Replace `WHATSAPP_BUSINESS_ACCOUNT_ID` and `PHONE_NUMBER_ID` with your actual values
- The `wa_id` `918309866859` is the test customer number
- Each button test simulates a user clicking the respective button
- The system will respond with appropriate messages for each button action
