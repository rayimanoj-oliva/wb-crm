# Zoho Lead Creation Integration Guide

## Overview
This integration provides comprehensive Zoho CRM lead creation functionality for the WhatsApp Lead-to-Appointment booking flow. It handles Q5 triggers for auto-dial events and termination events for follow-up/remarketing.

## Key Features

### 1. Q5 Auto-Dial Trigger
- **When**: User responds "Yes" to callback confirmation (Q5)
- **Action**: Creates lead with `CALL_INITIATED` status + triggers auto-dial event
- **Purpose**: Immediate callback for appointment confirmation

### 2. Termination Event Handling
- **When**: User drops off before Q5 OR responds "No" to Q5
- **Action**: Creates lead with `NO_CALLBACK` status for follow-up/remarketing
- **Purpose**: Lead nurturing and remarketing campaigns

### 3. Enhanced Lead Data Structure
- Uses your provided curl structure with proper field mapping
- Includes appointment details (city, clinic, date, time)
- Supports custom descriptions and preferences

## File Structure

```
controllers/components/lead_appointment_flow/
├── zoho_lead_service.py          # New enhanced service
├── zoho_integration.py           # Legacy integration (kept for compatibility)
├── callback_confirmation.py      # Updated to use Q5 trigger
├── flow_controller.py           # Updated to use new service
└── README.md                    # This file
```

## API Integration Details

### Lead Creation Endpoint
- **URL**: `https://www.zohoapis.in/crm/v2.1/Leads`
- **Method**: POST
- **Headers**: 
  - `Authorization: Zoho-oauthtoken {access_token}`
  - `Content-Type: application/json`
  - `Cookie: _zcsr_tmp=724cc9cf-75aa-4b3e-96dd-57ce0f42c37c; crmcsr=724cc9cf-75aa-4b3e-96dd-57ce0f42c37c; zalb_941ef25d4b=64bf0502158f6e506399625cae2049e9`

### Lead Data Structure
```json
{
    "data": [
        {
            "First_Name": "Customer Name",
            "Last_Name": "",
            "Email": "customer@email.com",
            "Phone": "919876543210",
            "Mobile": "919876543210",
            "City": "Delhi",
            "Lead_Source": "WhatsApp Lead-to-Appointment Flow",
            "Lead_Status": "CALL_INITIATED|PENDING|NO_CALLBACK",
            "Company": "Oliva Skin & Hair Clinic",
            "Description": "Lead from WhatsApp Lead-to-Appointment Flow | City: Delhi | Clinic: Main Branch | Preferred Date: 2024-01-15 | Preferred Time: 10:00 AM | Status: CALL_INITIATED"
        }
    ],
    "trigger": [
        "approval",
        "workflow",
        "blueprint"
    ]
}
```

## Usage Examples

### 1. Q5 Auto-Dial Event (User says "Yes" to callback)
```python
from controllers.components.lead_appointment_flow.zoho_lead_service import trigger_q5_auto_dial_event

result = await trigger_q5_auto_dial_event(
    db=db,
    wa_id="+919876543210",
    customer=customer_object,
    appointment_details={
        "selected_city": "Delhi",
        "selected_clinic": "Main Branch",
        "custom_date": "2024-01-15",
        "selected_time": "10:00 AM"
    }
)
```

### 2. Termination Event (User drops off or says "No")
```python
from controllers.components.lead_appointment_flow.zoho_lead_service import handle_termination_event

result = await handle_termination_event(
    db=db,
    wa_id="+919876543210",
    customer=customer_object,
    termination_reason="negative_q5_response",  # or "dropped_off_at_city_selection"
    appointment_details=appointment_details
)
```

### 3. Direct Lead Creation
```python
from controllers.components.lead_appointment_flow.zoho_lead_service import create_lead_for_appointment

result = await create_lead_for_appointment(
    db=db,
    wa_id="+919876543210",
    customer=customer_object,
    appointment_details=appointment_details,
    lead_status="PENDING",
    appointment_preference="Custom preference text"
)
```

## Lead Status Mapping

| Status | Description | Use Case |
|--------|-------------|----------|
| `CALL_INITIATED` | User requested callback (Q5 Yes) | Auto-dial triggered |
| `PENDING` | User completed flow but no callback | Manual follow-up |
| `NO_CALLBACK` | User dropped off or declined callback | Follow-up/remarketing |

## Configuration

### Environment Variables Required
```bash
ZOHO_CLIENT_ID=your_client_id
ZOHO_CLIENT_SECRET=your_client_secret
ZOHO_REFRESH_TOKEN=your_refresh_token
```

### Authentication
The service uses the existing `utils/zoho_auth.py` for token management. Make sure your refresh token is valid and has the necessary CRM permissions.

### Dedicated number constraint

This Lead-to-Appointment flow is restricted to a single WhatsApp Business number and must not be invoked from other numbers or flows.

- Configuration lives in `controllers/components/lead_appointment_flow/config.py`:
  - `LEAD_APPOINTMENT_PHONE_ID = "367633743092037"`
  - `LEAD_APPOINTMENT_DISPLAY_LAST10 = "7729992376"`
- The webhook router (`controllers/web_socket.py`) gates all lead-appointment triggers (text and template-buttons) to this phone only.
- Do not reference or import these lead flow files from other flows.

To change the dedicated number, update the constants above; no other code edits are required.

## Error Handling

The service includes comprehensive error handling:
- Token validation
- API response validation
- Exception logging with traceback
- Graceful fallbacks

## Testing

### Test Lead Creation
```bash
curl --location 'https://www.zohoapis.in/crm/v2.1/Leads' \
--header 'Authorization: Zoho-oauthtoken YOUR_ACCESS_TOKEN' \
--header 'Content-Type: application/json' \
--data-raw '{
    "data": [
        {
            "First_Name": "Test",
            "Last_Name": "User",
            "Email": "test@example.com",
            "Phone": "919876543210",
            "Mobile": "919876543210",
            "City": "Delhi",
            "Lead_Source": "WhatsApp Lead-to-Appointment Flow",
            "Lead_Status": "PENDING",
            "Company": "Oliva Skin & Hair Clinic",
            "Description": "Test lead creation"
        }
    ],
    "trigger": [
        "approval",
        "workflow",
        "blueprint"
    ]
}'
```

## Integration Points

### 1. Callback Confirmation Flow
- **File**: `callback_confirmation.py`
- **Q5 Yes**: Triggers `trigger_q5_auto_dial_event()`
- **Q5 No**: Triggers `handle_termination_event()`

### 2. Flow Controller
- **File**: `flow_controller.py`
- **Time Selection**: Creates lead with `PENDING` status
- **Dropoff Handling**: Creates lead with `NO_CALLBACK` status

### 3. WebSocket Integration
- All lead creation events are logged
- WebSocket broadcasts include lead creation status
- Real-time updates for admin dashboard

## Monitoring and Logging

### Debug Logs
All operations include detailed debug logging:
```
[zoho_lead_service] DEBUG - Starting lead creation for +919876543210
[zoho_lead_service] DEBUG - Lead status: CALL_INITIATED
[zoho_lead_service] DEBUG - User details from session: John Doe, 9876543210
[zoho_lead_service] DEBUG - Appointment details from session: Delhi, Main Branch, 2024-01-15, 10:00 AM
[zoho_lead_service] DEBUG - Lead created successfully: +919876543210, Name: John Doe, Lead ID: 123456789
```

### Error Logs
```
[zoho_lead_service] ERROR - Lead creation failed: +919876543210, Error: API Error 401: Invalid token
[zoho_lead_service] ERROR - Q5 auto-dial event failed: Exception: Connection timeout
```

## Future Enhancements

1. **Auto-Dial API Integration**: Connect to actual auto-dial service
2. **Lead Scoring**: Implement lead scoring based on engagement
3. **Follow-up Automation**: Automated follow-up sequences
4. **Analytics Dashboard**: Lead conversion tracking
5. **A/B Testing**: Test different lead creation strategies

## Troubleshooting

### Common Issues

1. **Token Expired**
   - Check refresh token validity
   - Verify client credentials

2. **API Rate Limits**
   - Implement retry logic
   - Add rate limiting

3. **Field Validation Errors**
   - Check required field mapping
   - Validate data types

4. **Session Data Missing**
   - Ensure proper session state management
   - Add fallback data sources

### Support
For issues or questions, check the debug logs first and ensure all environment variables are properly configured.