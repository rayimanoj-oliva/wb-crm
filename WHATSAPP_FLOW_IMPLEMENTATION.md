# WhatsApp Flow Implementation for Address Collection

## Overview

This implementation adds **WhatsApp Flow** support to the address collection system, allowing users to fill out structured forms directly within WhatsApp, similar to JioMart, Blinkit, and Domino's.

## What is WhatsApp Flow?

**WhatsApp Flow** is an interactive feature that allows businesses to create structured forms within WhatsApp messages. When users tap a flow button, it opens a native form interface where they can fill out information in a structured way.

### Key Features:
- **Native Form Interface**: Opens within WhatsApp app
- **Structured Data Collection**: Organized fields and validation
- **Professional UX**: Matches modern e-commerce standards
- **Real-time Validation**: Field validation as users type
- **Mobile Optimized**: Designed for mobile devices

## Implementation Details

### 1. Flow Button Creation

#### Template Structure:
```json
{
  "messaging_product": "whatsapp",
  "to": "wa_id",
  "type": "interactive",
  "interactive": {
    "type": "flow",
    "header": {
      "type": "text",
      "text": "📍 Address Collection"
    },
    "body": {
      "text": "Please provide your delivery address using the form below."
    },
    "footer": {
      "text": "All fields are required for delivery"
    },
    "action": {
      "name": "flow",
      "parameters": {
        "flow_message_version": "3",
        "flow_token": "address_flow_wa_id_timestamp",
        "flow_id": "address_collection_flow",
        "flow_cta": "Provide Address",
        "flow_action_payload": {
          "customer_name": "Customer",
          "flow_type": "address_collection"
        }
      }
    }
  }
}
```

### 2. Flow Response Handling

#### Flow Response Structure:
```json
{
  "interactive": {
    "type": "flow",
    "flow_response": {
      "flow_token": "address_flow_wa_id_timestamp",
      "flow_id": "address_collection_flow",
      "flow_cta": "Provide Address",
      "flow_action_payload": {
        "full_name": "John Doe",
        "phone_number": "9876543210",
        "house_street": "123 Main Street",
        "locality": "Downtown",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001",
        "landmark": "Near Central Mall"
      }
    }
  }
}
```

### 3. Field Mapping

The system maps various field names to standard address fields:

```python
field_mappings = {
    "full_name": ["full_name", "name", "customer_name"],
    "phone_number": ["phone_number", "phone", "mobile"],
    "house_street": ["house_street", "address_line_1", "street"],
    "locality": ["locality", "area", "neighborhood"],
    "city": ["city", "town"],
    "state": ["state", "province"],
    "pincode": ["pincode", "postal_code", "zip_code"],
    "landmark": ["landmark", "landmark_nearby"]
}
```

## Setup Instructions

### 1. Create Flow in Meta Business Manager

1. **Go to Meta Business Manager**
2. **Navigate to WhatsApp Business Platform**
3. **Create a new Flow**:
   - Flow ID: `address_collection_flow`
   - Flow Name: "Address Collection Form"
   - Flow Type: "Data Collection"

### 2. Design the Flow Form

#### Required Fields:
- **Full Name** (Text Input)
- **Phone Number** (Phone Input)
- **House & Street** (Text Input)
- **Area/Locality** (Text Input)
- **City** (Text Input)
- **State** (Text Input)
- **Pincode** (Number Input, 6 digits)
- **Landmark** (Text Input, Optional)

#### Form Structure:
```
📍 Address Collection Form
├── Contact Details
│   ├── Full Name *
│   └── Phone Number *
└── Address Details
    ├── Pincode *
    ├── House & Street *
    ├── Area/Locality *
    ├── City *
    ├── State *
    └── Landmark (Optional)
```

### 3. Configure Flow Settings

#### Flow Configuration:
- **Flow ID**: `address_collection_flow`
- **Flow Version**: `3`
- **CTA Text**: "Provide Address"
- **Validation**: Enable field validation
- **Required Fields**: Mark required fields with *

### 4. Update collect_address Template

In your `collect_address` template, add a flow button:

```json
{
  "type": "interactive",
  "interactive": {
    "type": "flow",
    "action": {
      "name": "flow",
      "parameters": {
        "flow_message_version": "3",
        "flow_id": "address_collection_flow",
        "flow_cta": "Provide Address"
      }
    }
  }
}
```

## Code Implementation

### 1. Flow Button Function

```python
async def send_address_flow_button(wa_id: str, db: Session, customer_name: str = "Customer"):
    """Send WhatsApp Flow button for address collection"""
    # Implementation in controllers/web_socket.py
```

### 2. Flow Response Handler

```python
# Handle WhatsApp Flow submission
if i_type == "flow":
    flow_response = interactive.get("flow_response", {})
    # Process flow data and save address
```

### 3. Button Handling

```python
# Handle WhatsApp Flow buttons
if btn_id in ["provide_address", "address_flow"]:
    await send_address_flow_button(wa_id, db, customer.name or "Customer")
```

## User Experience Flow

### 1. Order Placement
```
User places order → collect_address template sent
```

### 2. Template with Flow Button
```
User receives template with "Provide Address" flow button
```

### 3. Flow Form Opens
```
User taps button → Native form opens in WhatsApp
```

### 4. Form Completion
```
User fills form → Data validated → Form submitted
```

### 5. Address Saved
```
System processes data → Address saved → Payment flow continues
```

## Benefits

### 1. **Professional UX**
- Native form interface within WhatsApp
- Structured field layout
- Real-time validation

### 2. **Better Data Quality**
- Required field validation
- Format validation (phone, pincode)
- Structured data collection

### 3. **Mobile Optimized**
- Designed for mobile devices
- Touch-friendly interface
- Fast data entry

### 4. **Reduced Errors**
- Field validation prevents errors
- Clear field labels and hints
- Structured data format

## Testing

### 1. Test Flow Button
```python
# Test sending flow button
await send_address_flow_button("917729992376", db, "Test Customer")
```

### 2. Test Flow Response
```python
# Simulate flow response
flow_response = {
    "flow_id": "address_collection_flow",
    "flow_action_payload": {
        "full_name": "John Doe",
        "phone_number": "9876543210",
        "house_street": "123 Main Street",
        "locality": "Downtown",
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": "400001"
    }
}
```

## Troubleshooting

### 1. Flow Not Opening
- Check flow ID matches Meta Business Manager
- Verify flow is published and active
- Check flow permissions

### 2. Data Not Received
- Check flow_action_payload structure
- Verify field mappings
- Check flow response handling

### 3. Validation Errors
- Check required field validation
- Verify field format validation
- Check error handling logic

## Next Steps

1. **Create Flow in Meta Business Manager**
2. **Test Flow Button Sending**
3. **Test Flow Form Completion**
4. **Verify Address Saving**
5. **Test Payment Flow Integration**

## Files Modified

- `controllers/web_socket.py` - Added flow handling
- `utils/address_templates.py` - Added flow templates
- `WHATSAPP_FLOW_IMPLEMENTATION.md` - This documentation

## Conclusion

The WhatsApp Flow implementation provides a professional, structured way to collect address information directly within WhatsApp, matching the user experience of leading e-commerce platforms like JioMart, Blinkit, and Domino's.

The system automatically handles flow responses, validates data, saves addresses, and continues with the payment flow, providing a seamless user experience from order placement to payment completion.
