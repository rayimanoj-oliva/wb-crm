# Fix Summary: Zoho Concern Name Now Appears in Leads

## Problem
The Zoho concern/treatment name was NOT appearing in the lead description when created from the treatment flow.

## Root Cause
When the lead was being created from the treatment flow (after user confirms name/phone), the system wasn't:
1. Retrieving the selected concern from `appointment_state`
2. Passing it to the lead creation function
3. Looking it up in `appointment_details` as a fallback

## Solution Implemented

### 1. Updated `web_socket.py` (lines 2028-2041)
**Added**: Retrieve selected concern from state and pass it to appointment_details

```python
# Get selected concern from appointment_state
selected_concern = (st or {}).get("selected_concern")
print(f"[treatment_flow] DEBUG - Selected concern from state: {selected_concern}")

# Prepare appointment details for treatment flow
appointment_details = {
    "flow_type": "treatment_flow",
    "treatment_selected": True,
    "no_scheduling_required": True,
    "corrected_name": name_final,
    "corrected_phone": phone_final,
    "selected_concern": selected_concern  # ← Added this!
}
```

### 2. Updated `zoho_lead_service.py` (lines 257-330)
**Added**: Handle selected concern from appointment_details as fallback

```python
# Initialize variables for concern tracking
selected_concern = None
zoho_mapped_concern = None
city = "Unknown"
clinic = "Unknown"
appointment_date = "Not specified"
appointment_time = "Not specified"

# ... in exception handler ...
# Try to get selected concern from appointment_details if not in state
if not selected_concern and appointment_details:
    selected_concern = appointment_details.get("selected_concern")
    if selected_concern:
        print(f"[LEAD APPOINTMENT FLOW] Got concern from appointment_details: {selected_concern}")
        zoho_mapped_concern = get_zoho_name(db, selected_concern)
```

## Result
Now when a lead is created:
- The selected concern is retrieved from state ✅
- The Zoho name is looked up from the mapping table ✅
- The description includes: `"Treatment/Zoho Concern: [Zoho Name]"` ✅

## Example Lead Description (After Fix)
```
Lead from WhatsApp Lead-to-Appointment Flow | 
City: Unknown | 
Clinic: Unknown | 
Preferred Date: Not specified | 
Preferred Time: Not specified | 
Treatment/Zoho Concern: Acne |  ← NOW APPEARS!
Preference: Treatment consultation - no specific appointment time requested | 
Status: PENDING
```

## Testing
To verify the fix works:
1. User selects a treatment concern (e.g., "Acne / Acne Scars")
2. System stores it in appointment_state
3. User completes appointment with name/phone
4. Lead creation retrieves concern and maps to "Acne"
5. Lead description includes "Treatment/Zoho Concern: Acne"

## Status
✅ Fixed - Zoho concern names will now appear in lead descriptions

