import json
from typing import Any, Dict

def debug_webhook_payload(body: Dict[str, Any], raw_body: str | None = None) -> None:
    try:
        print(f"[webhook_debug] Payload keys: {list(body.keys())}")
        if "entry" in body:
            entry = body["entry"][0] if body["entry"] else {}
            print(f"[webhook_debug] Entry ID: {entry.get('id', 'N/A')}")
            if "changes" in entry:
                change = entry["changes"][0] if entry["changes"] else {}
                print(f"[webhook_debug] Change field: {change.get('field', 'N/A')}")
                value = change.get("value", {})
                print(f"[webhook_debug] Value keys: {list(value.keys())}")
                if "messages" in value:
                    messages = value["messages"]
                    print(f"[webhook_debug] Message count: {len(messages)}")
                    for i, msg in enumerate(messages):
                        print(f"[webhook_debug] Message {i}: type={msg.get('type', 'N/A')}, id={msg.get('id', 'N/A')}")
                        if msg.get("type") == "interactive":
                            interactive = msg.get("interactive", {})
                            print(f"[webhook_debug] Interactive type: {interactive.get('type', 'N/A')}")
                            if interactive.get("type") == "nfm_reply":
                                nfm = interactive.get("nfm_reply", {})
                                response_json = nfm.get("response_json", "")
                                print(f"[webhook_debug] NFM response_json length: {len(response_json)}")
                                print(f"[webhook_debug] NFM response_json preview: {response_json[:200]}...")
                                if response_json.endswith('...') or len(response_json) < 50:
                                    print(f"[webhook_debug] WARNING - Possible truncation detected!")
                                try:
                                    parsed = json.loads(response_json)
                                    print(f"[webhook_debug] NFM parsed keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'Not a dict'}")
                                    print(f"[webhook_debug] NFM parsed values: {parsed}")
                                    has_template_vars = any("{{" in str(v) and "}}" in str(v) for v in (parsed.values() if isinstance(parsed, dict) else []))
                                    if has_template_vars:
                                        print(f"[webhook_debug] WARNING - Template variables detected in parsed data!")
                                    if isinstance(parsed, dict):
                                        empty_values = [k for k, v in parsed.items() if not v or (isinstance(v, str) and not v.strip())]
                                        if empty_values:
                                            print(f"[webhook_debug] WARNING - Empty values found: {empty_values}")
                                except json.JSONDecodeError as e:
                                    print(f"[webhook_debug] ERROR - Invalid JSON in NFM response: {e}")
        if raw_body:
            print(f"[webhook_debug] Raw body length: {len(raw_body)}")
            print(f"[webhook_debug] Raw body preview: {raw_body[:300]}...")
    except Exception as e:
        print(f"[webhook_debug] ERROR - Debug function failed: {e}")

def debug_flow_data_extraction(flow_payload: Dict[str, Any], extracted_data: Dict[str, Any]) -> None:
    try:
        print(f"[flow_debug] Flow payload keys: {list(flow_payload.keys())}")
        print(f"[flow_debug] Flow payload values: {flow_payload}")
        print(f"[flow_debug] Extracted data keys: {list(extracted_data.keys())}")
        print(f"[flow_debug] Extracted data values: {list(extracted_data.values())}")
        common_fields = ["name", "phone", "address", "city", "state", "pincode", "zipcode"]
        found_fields = [f for f in common_fields if any(f in key.lower() for key in flow_payload.keys())]
        print(f"[flow_debug] Common fields found in payload: {found_fields}")
        for key, value in flow_payload.items():
            if isinstance(value, dict):
                print(f"[flow_debug] Nested object '{key}': {value}")
            elif isinstance(value, list):
                print(f"[flow_debug] Array '{key}': {value}")
    except Exception as e:
        print(f"[flow_debug] ERROR - Debug function failed: {e}")
