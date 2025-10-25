# WhatsApp Lead-to-Appointment Booking Flow (Oliva Clinics)

## Overview

This module implements a complete automated WhatsApp flow for converting Meta ad clicks into appointment bookings. The flow is designed to handle users who click "Inquire" or "Book now" buttons on Meta (Facebook/Instagram) ads and are redirected to the WhatsApp chatbot.

## Flow Architecture

The flow consists of several interconnected components:

```
Meta Ad Click → WhatsApp Chat → Auto-Welcome → City Selection → Clinic Location → Time Slot → Callback Confirmation → Zoho CRM Integration
```

## Components

### 1. Auto Welcome (`auto_welcome.py`)
- **Trigger**: Text messages containing keywords like "hi", "hello", "book", "appointment", "inquire"
- **Action**: Sends welcome message with Yes/No buttons
- **Buttons**: 
  - ✅ Yes, I'd like to book
  - ❌ Not now

### 2. City Selection (`city_selection.py`)
- **Trigger**: User selects "Yes, I'd like to book"
- **Action**: Shows list of available cities
- **Options**: Hyderabad, Bengaluru, Chennai, Pune, Kochi, Other

### 3. Clinic Location (`clinic_location.py`)
- **Trigger**: User selects a city
- **Action**: Shows clinic locations for the selected city
- **Dynamic**: Clinic list changes based on selected city

### 4. Time Slot Selection (`time_slot_selection.py`)
- **Trigger**: User selects a clinic
- **Action**: Shows time slot options
- **Options**: 
  - This week
  - Next week
  - Custom date (with text input)

### 5. Callback Confirmation (`callback_confirmation.py`)
- **Trigger**: User completes time slot selection
- **Action**: Asks for callback preference
- **Buttons**:
  - 📞 Yes, please call me (triggers Zoho Auto-Dial)
  - 💬 No, just keep my details (creates lead only)

### 6. Zoho Integration (`zoho_integration.py`)
- **Auto-Dial**: Triggers Zoho CRM auto-dial for callback requests
- **Lead Creation**: Creates leads in Zoho CRM with appropriate status
- **Status Types**:
  - `CALL_INITIATED`: User wants callback
  - `PENDING`: User doesn't want callback
  - `NO_CALLBACK`: User dropped off or said "not now"

### 7. Flow Controller (`flow_controller.py`)
- **Main Orchestrator**: Coordinates the entire flow
- **State Management**: Tracks user progress through the flow
- **Integration**: Handles both text and interactive responses

## Session State Management

The flow uses `lead_appointment_state` dictionary in `web_socket.py` to track user progress:

```python
lead_appointment_state = {
    "wa_id": {
        "selected_city": "Hyderabad",
        "selected_clinic": "Banjara Hills",
        "custom_date": "2024-12-25",
        "waiting_for_custom_date": False,
        "clinic_id": "clinic_hyderabad_banjara"
    }
}
```

## Integration Points

### Webhook Integration
The flow is integrated into the main webhook controller (`web_socket.py`) and runs after the treatment flow:

```python
# Lead-to-Appointment Flow runs after treatment flow
if not handled_text:
    lead_result = await run_lead_appointment_flow(...)
```

### Existing Flow Compatibility
- Uses existing slot selection system from `interactive_type.py`
- Leverages existing time slot categories and time lists
- Maintains compatibility with existing appointment booking flow

## Termination Rules

The flow handles various termination scenarios:

1. **User drops off before Q5**: Creates lead with `NO_CALLBACK` status
2. **User selects "Not now"**: Creates lead with `NO_CALLBACK` status
3. **User selects "No callback"**: Creates lead with `PENDING` status
4. **User selects "Yes callback"**: Creates lead with `CALL_INITIATED` status and triggers auto-dial

## Zoho CRM Integration

### Lead Creation
Creates leads with the following structure:
- **First_Name**: Customer name
- **Phone**: WhatsApp ID (formatted as Indian phone number)
- **Email**: Customer email (if available)
- **Lead_Source**: "WhatsApp Lead-to-Appointment Flow"
- **Lead_Status**: Based on user choice (CALL_INITIATED, PENDING, NO_CALLBACK)
- **Description**: Includes appointment details and preferences
- **City**: Selected city
- **Custom Fields**: Clinic, appointment date, WhatsApp ID

### Auto-Dial Trigger
Triggers Zoho auto-dial with:
- Customer phone number
- Appointment details
- Callback reason
- Priority level

## Usage

### Triggering the Flow
The flow can be triggered by:
1. **Meta Ad Click**: Users clicking "Inquire" or "Book now" buttons
2. **Text Messages**: Keywords like "hi", "hello", "book", "appointment"
3. **Manual Trigger**: Direct function calls

### Flow Progression
```python
# Auto-welcome
await send_auto_welcome_message(db, wa_id=wa_id)

# City selection
await send_city_selection(db, wa_id=wa_id)

# Clinic location
await send_clinic_location(db, wa_id=wa_id, city="Hyderabad")

# Time slot selection
await send_time_slot_selection(db, wa_id=wa_id)

# Callback confirmation
await send_callback_confirmation(db, wa_id=wa_id)
```

## Error Handling

The flow includes comprehensive error handling:
- **Token Issues**: Falls back to text messages
- **API Failures**: Graceful degradation
- **Invalid Inputs**: User-friendly error messages
- **Session Management**: Automatic cleanup

## Testing

To test the flow:

1. **Start Flow**: Send "hi" or "book appointment" to trigger auto-welcome
2. **Follow Steps**: Select city, clinic, time slot, callback preference
3. **Check Zoho**: Verify lead creation and auto-dial trigger
4. **Session State**: Monitor `lead_appointment_state` for progress tracking

## Configuration

### Environment Variables
- `ZOHO_CLIENT_ID`: Zoho CRM client ID
- `ZOHO_CLIENT_SECRET`: Zoho CRM client secret
- `ZOHO_REFRESH_TOKEN`: Zoho CRM refresh token
- `WHATSAPP_PHONE_ID`: WhatsApp Business phone ID
- `WHATSAPP_DISPLAY_NUMBER`: WhatsApp display number

### Customization
- **Cities**: Modify `get_clinics_for_city()` in `clinic_location.py`
- **Clinics**: Update clinic mapping in `clinic_location.py`
- **Time Slots**: Leverage existing slot system in `interactive_type.py`
- **Zoho Fields**: Modify lead creation payload in `zoho_integration.py`

## Future Enhancements

Potential improvements:
1. **Database Storage**: Move session state to database
2. **Analytics**: Track conversion rates and drop-off points
3. **A/B Testing**: Test different flow variations
4. **Multi-language**: Support for multiple languages
5. **Integration**: Connect with calendar systems for real-time availability
