import uuid
from typing import Dict

# In-memory store: { wa_id: True/False }
awaiting_address_users: Dict[str, bool] = {}
# Track whether we've already nudged the user to use the form to avoid repeats
address_nudge_sent: Dict[str, bool] = {}

# In-memory appointment scheduling state per user
# Structure: { wa_id: { "date": "YYYY-MM-DD" } }
appointment_state: Dict[str, dict] = {}

# In-memory lead appointment flow state per user
# Structure: { wa_id: { "selected_city": str, "selected_clinic": str,
# "custom_date": str, "waiting_for_custom_date": bool, "clinic_id": str } }
lead_appointment_state: Dict[str, dict] = {}

# Flow token storage
flow_tokens: Dict[str, str] = {}

def generate_flow_token(wa_id: str) -> str:
    token = str(uuid.uuid4())
    flow_tokens[wa_id] = token
    return token


def clear_flow_state_for_restart(wa_id: str) -> None:
    """
    Clear stale flow state to allow a customer to start a new flow.
    
    This function should be called when detecting a starting point message
    to ensure old state doesn't prevent a new flow from starting.
    
    Args:
        wa_id: The WhatsApp ID of the customer
    """
    try:
        # Clear appointment state flags that prevent flow restart
        if wa_id in appointment_state:
            state = appointment_state[wa_id]
            # Clear mr_welcome_sent flag to allow welcome message to be sent again
            state.pop("mr_welcome_sent", None)
            # Clear sending timestamp to allow immediate restart
            state.pop("mr_welcome_sending_ts", None)
            # If state is empty or only has non-critical fields, clear it entirely
            # Keep only essential fields like treatment_flow_phone_id if needed
            critical_fields = {"treatment_flow_phone_id"}
            if not any(k in critical_fields for k in state.keys()):
                appointment_state.pop(wa_id, None)
            else:
                # Keep only critical fields
                appointment_state[wa_id] = {k: v for k, v in state.items() if k in critical_fields}
        
        # Clear lead appointment state to allow fresh start
        if wa_id in lead_appointment_state:
            lead_appointment_state.pop(wa_id, None)
        
        print(f"[state/memory] DEBUG - Cleared flow state for restart: wa_id={wa_id}")
    except Exception as e:
        print(f"[state/memory] WARNING - Error clearing flow state: {e}")