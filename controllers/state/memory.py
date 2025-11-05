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
