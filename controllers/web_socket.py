from datetime import datetime, timedelta
from http.client import HTTPException

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, APIRouter
from fastapi.params import Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any
import re
import mimetypes
import asyncio
import os
import json
import requests
import uuid

from sqlalchemy.orm import Session
from starlette.responses import PlainTextResponse

from database.db import get_db
from schemas.orders_schema import OrderItemCreate,OrderCreate, PaymentCreate
from services import customer_service, message_service, order_service
from services import payment_service
from schemas.customer_schema import CustomerCreate
from schemas.message_schema import MessageCreate
from models.models import Message
from utils.whatsapp import send_message_to_waid
from marketing.name_validator import validate_human_name
from marketing.phone_validator import validate_indian_phone
from services.whatsapp_service import get_latest_token
from config.constants import get_messages_url, get_media_url

# =============================================================================
# WHATSAPP FLOW HANDLING
# =============================================================================
# WhatsApp Flows are designed in Meta Business Manager's Flow Builder.
# The flow fields, validation, and UI are defined there, not in this code.
# This code only handles the webhook response when users complete the flow.
from utils.razorpay_utils import create_razorpay_payment_link
from utils.ws_manager import manager
from controllers.utils.debug_window import debug_webhook_payload,debug_flow_data_extraction
from utils.shopify_admin import update_variant_price
from utils.address_validator import analyze_address, format_errors_for_user
from controllers.components.welcome_flow import run_welcome_flow, trigger_buy_products_from_welcome
from marketing.flows import run_treament_flow, run_treatment_buttons_flow
from controllers.components.interactive_type_clean import run_interactive_type
from controllers.components.lead_appointment_flow import run_lead_appointment_flow
from controllers.components.number_flows.mr_welcome.flow import run_mr_welcome_number_flow
from controllers.components.products_flow import run_buy_products_flow
from marketing.whatsapp_numbers import get_number_config

# Webhook verification token
VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "default_verify_token")

# Manoj Changes
from controllers.ws_channel import router
from controllers.services import *

from controllers.services.appointments import *
from controllers.utils.media_upload import *
from controllers.state.memory import *

@router.post("/webhook")
async def receive_message(request: Request, db: Session = Depends(get_db)):
    try:
        # CRITICAL: Capture raw request body BEFORE JSON parsing to avoid truncation
        raw_body = await request.body()
        raw_body_str = raw_body.decode("utf-8", errors="replace")
        
        # Parse JSON from raw body
        try:
            body = json.loads(raw_body_str)
        except json.JSONDecodeError as e:
            print(f"[ws_webhook] ERROR - Invalid JSON in webhook payload: {e}")
            print(f"[ws_webhook] Raw body: {raw_body_str[:500]}...")
            return {"status": "error", "message": "Invalid JSON payload"}
        
        # Persist raw webhook payload to file for debugging/auditing
        try:
            log_dir = "webhook_logs"
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_path = os.path.join(log_dir, f"webhook_{ts}.json")

            # Write the complete raw body to ensure no truncation
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write(raw_body_str)
                
            # Also create a formatted version for easier debugging
            formatted_path = os.path.join(log_dir, f"webhook_{ts}_formatted.json")
            try:
                formatted_json = json.dumps(body, ensure_ascii=False, indent=2, default=str)
                with open(formatted_path, "w", encoding="utf-8") as lf:
                    lf.write(formatted_json)
            except Exception as e:
                print(f"[ws_webhook] WARN - Could not create formatted log: {e}")

        except Exception as e:
            print(f"[ws_webhook] WARN - webhook logging failed: {e}")
        
        # Enhanced debugging for webhook payloads
        debug_webhook_payload(body, raw_body_str)
        
        # Check if this is a status update (not a message) - skip it
        if "entry" in body:
            value = body["entry"][0]["changes"][0]["value"]
            # If value contains 'statuses' but no 'messages' or 'contacts', it's a status update
            if "statuses" in value and ("messages" not in value or "contacts" not in value):
                print(f"[ws_webhook] DEBUG - Skipping status update webhook")
                return {"status": "ok", "message": "Status update ignored"}
        elif "statuses" in body and ("messages" not in body or "contacts" not in body):
            print(f"[ws_webhook] DEBUG - Skipping status update webhook (alternative structure)")
            return {"status": "ok", "message": "Status update ignored"}
        
        # Handle different payload structures and extract phone_number_id early
        phone_number_id = None
        value = None
        
        if "entry" in body:
            # Standard WhatsApp Business API webhook structure
            print(f"[ws_webhook] DEBUG - Using standard webhook structure")
            value = body["entry"][0]["changes"][0]["value"]
            
            # Verify we have messages and contacts
            if "messages" not in value or "contacts" not in value:
                print(f"[ws_webhook] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[ws_webhook] Available keys in value: {list(value.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = value["contacts"][0]
            message = value["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = value["metadata"]["display_phone_number"]
            
            # Extract phone_number_id from metadata
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            print(f"[ws_webhook] DEBUG - phone_number_id from metadata: {phone_number_id}")

            # EARLY: treatment-only marketing handler for the two numbers
            try:
                from marketing.controllers.web_socket_marketing import handle_marketing_event  # type: ignore
                mk_res = await handle_marketing_event(db, value=value)
                mk_status = (mk_res or {}).get("status")
                if mk_status in {"welcome_restart", "handled"}:
                    print(f"[ws_webhook] DEBUG - Marketing handler returned early with status={mk_status}")
                    return mk_res
                elif mk_status == "ignored":
                    print(f"[ws_webhook] DEBUG - Marketing handler deferred (status=ignored), continuing to main handler")
            except Exception as e:
                print(f"[ws_webhook] WARNING - Marketing handler exception: {e}")
                pass
        else:
            # Alternative payload structure (direct structure)
            print(f"[ws_webhook] DEBUG - Using alternative payload structure")
            
            # Verify we have messages and contacts
            if "messages" not in body or "contacts" not in body:
                print(f"[ws_webhook] ERROR - Missing 'messages' or 'contacts' in webhook payload")
                print(f"[ws_webhook] Available keys in body: {list(body.keys())}")
                return {"status": "error", "message": "Invalid webhook payload"}
            
            contact = body["contacts"][0]
            message = body["messages"][0]
            wa_id = contact["wa_id"]
            sender_name = contact["profile"]["name"]
            from_wa_id = message["from"]
            to_wa_id = body.get("phone_number_id", "367633743092037")
            phone_number_id = body.get("phone_number_id")
            print(f"[ws_webhook] DEBUG - phone_number_id from body: {phone_number_id}")
        
        # =============================================================================
        # EARLY ROUTING BASED ON phone_number_id
        # =============================================================================
        # Route messages to appropriate flow handlers based on the receiving phone number
        phone_number_id_str = str(phone_number_id) if phone_number_id else None
        print(f"[ws_webhook] DEBUG - Routing decision: phone_number_id={phone_number_id_str}")
        
        # Import flow identifiers
        try:
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            from controllers.components.lead_appointment_flow.config import LEAD_APPOINTMENT_PHONE_ID
        except Exception as e:
            print(f"[ws_webhook] WARNING - Could not import flow configs: {e}")
            TREATMENT_FLOW_ALLOWED_PHONE_IDS = set()
            LEAD_APPOINTMENT_PHONE_ID = None
        
        # Determine flow context based on phone_number_id
        is_treatment_flow_number = phone_number_id_str in TREATMENT_FLOW_ALLOWED_PHONE_IDS if phone_number_id_str else False
        is_lead_appointment_number = phone_number_id_str == str(LEAD_APPOINTMENT_PHONE_ID) if (phone_number_id_str and LEAD_APPOINTMENT_PHONE_ID) else False
        
        print(f"[ws_webhook] DEBUG - Flow routing: is_treatment={is_treatment_flow_number}, is_lead_appointment={is_lead_appointment_number}")
        
        # Store flow context in state for downstream handlers
        try:
            st_route = appointment_state.get(wa_id) or {}
            if is_treatment_flow_number:
                st_route["flow_context"] = "treatment"
                st_route["from_treatment_flow"] = True
                st_route["treatment_flow_phone_id"] = phone_number_id_str
            elif is_lead_appointment_number:
                st_route["flow_context"] = "lead_appointment"
            appointment_state[wa_id] = st_route
        except Exception:
            pass
        timestamp = datetime.fromtimestamp(int(message["timestamp"]))
        message_type = message["type"]
        message_id = message["id"]
        
        # Initialize interactive variables for all message types
        interactive = message.get("interactive", {}) if message_type == "interactive" else {}
        i_type = interactive.get("type") if message_type == "interactive" else None

        # Derive a text body for non-text messages (interactive/list/button) so parsers work
        body_text = ""
        try:
            if message_type == "text":
                body_text = message[message_type].get("body", "")
            elif message_type == "interactive":
                it = message.get("interactive", {})
                if it.get("type") == "button_reply":
                    br = it.get("button_reply", {})
                    # Include both title and id to help downstream parsers (e.g., time_10_00)
                    body_text = " ".join(filter(None, [br.get("title"), br.get("id")]))
                elif it.get("type") == "list_reply":
                    lr = it.get("list_reply", {})
                    # Include both title and id to help downstream parsers (e.g., date_2025-10-01)
                    body_text = " ".join(filter(None, [lr.get("title"), lr.get("id")]))
                elif it.get("type") == "nfm_reply":
                    # Handle Native Flow Message reply - extract meaningful data
                    nfm = it.get("nfm_reply", {})
                    response_json = nfm.get("response_json", "{}")
                    try:
                        response_data = json.loads(response_json)
                        # Create a meaningful body text from the form data using mapped field names
                        form_fields = []
                        for key, value in response_data.items():
                            if value and str(value).strip() and not ("{{" in str(value) and "}}" in str(value)):
                                # Use user-friendly field names for display
                                display_names = {
                                    "full_name": "Name",
                                    "phone_number": "Phone", 
                                    "house_street": "Address",
                                    "pincode": "Pincode",
                                    "city": "City",
                                    "state": "State"
                                }
                                display_key = display_names.get(key, key)
                                form_fields.append(f"{display_key}: {value}")
                        body_text = " | ".join(form_fields) if form_fields else "Form submitted"
                        print(f"[ws_webhook] DEBUG - NFM body_text: {body_text}")
                    except Exception as e:
                        body_text = "Form submitted"
                        print(f"[ws_webhook] DEBUG - NFM body_text fallback: {e}")
                elif it.get("type") == "flow":
                    # Handle flow response
                    flow_response = it.get("flow_response", {})
                    flow_payload = flow_response.get("flow_action_payload", {})
                    if flow_payload:
                        form_fields = []
                        for key, value in flow_payload.items():
                            if value and str(value).strip():
                                form_fields.append(f"{key}: {value}")
                        body_text = " | ".join(form_fields) if form_fields else "Flow submitted"
                    else:
                        body_text = "Flow submitted"
            elif message_type == "button":
                btn = message.get("button", {})
                body_text = btn.get("text") or btn.get("payload") or ""
        except Exception:
            body_text = ""
        handled_text = False

        # Check prior messages first (before any early returns)
        prior_messages = message_service.get_messages_by_wa_id(db, wa_id)

        # Fetch or create customer
        customer = customer_service.get_or_create_customer(db, CustomerCreate(wa_id=wa_id, name=sender_name))

        # Track referrer information on EVERY message
        if body_text:
            try:
                from services.referrer_service import referrer_service
                
                # Get referrer URL from request headers if available
                referrer_url = (
                    request.headers.get("referer", "")
                    or request.headers.get("referrer", "")
                    or request.headers.get("x-forwarded-referer", "")
                    or request.headers.get("x-forwarded-referrer", "")
                    or request.headers.get("origin", "")
                )

                # Also include any query params on the webhook URL itself (defensive in prod)
                request_query = str(request.url.query) if getattr(request, "url", None) else ""
                combined_body = (
                    f"{body_text}&{request_query}" if request_query else body_text
                )
                
                # Track message interaction and extract UTM parameters
                referrer_record = referrer_service.track_message_interaction(db, wa_id, combined_body, referrer_url)
                
                if referrer_record:
                    print(f"Referrer tracking completed for {wa_id}")
                    try:
                        print(f"Center: {referrer_record.center_name}")
                        print(f"Location: {referrer_record.location}")
                        print(f"Appointment Date: {getattr(referrer_record, 'appointment_date', None)}")
                        print(f"Appointment Time: {getattr(referrer_record, 'appointment_time', None)}")
                        print(f"Treatment: {getattr(referrer_record, 'treatment_type', None)}")
                    except Exception:
                        pass
                else:
                    # Add explicit diagnostics to understand prod behavior
                    print("Referrer tracking yielded no record. Diagnostics:")
                    print(f"Headers referer={request.headers.get('referer', '')}")
                    print(f"Headers referrer={request.headers.get('referrer', '')}")
                    print(f"Headers x-forwarded-referer={request.headers.get('x-forwarded-referer', '')}")
                    print(f"Headers x-forwarded-referrer={request.headers.get('x-forwarded-referrer', '')}")
                    print(f"origin={request.headers.get('origin', '')}")
                    print(f"request_query={request_query}")
                    
            except Exception as e:
                print(f"Error tracking referrer: {e}")
                import traceback
                traceback.print_exc()

        # Check for appointment booking in any message (not just first message)
        if body_text:
            try:
                from services.referrer_service import referrer_service
                
                # Extract appointment information from message
                appointment_info = referrer_service.extract_appointment_info_from_message(body_text)
                
                # Allow interim updates (date-only or time-only), and finalize when both are present
                if appointment_info['appointment_date'] or appointment_info['appointment_time']:
                    print(f"Appointment booking detected for {wa_id}: {appointment_info}")
                    
                    # Try to update existing referrer record
                    # Preserve existing treatment if the current message doesn't include one
                    try:
                        existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                        existing_treat = getattr(existing_ref, 'treatment_type', None) if existing_ref else None
                    except Exception:
                        existing_treat = None

                    updated_referrer = referrer_service.update_appointment_booking(
                        db, 
                        wa_id, 
                        appointment_info['appointment_date'],
                        appointment_info['appointment_time'] or '',
                        appointment_info['treatment_type'] or existing_treat or ''
                    )
                    
                    if updated_referrer:
                        print(f"Successfully updated appointment booking for {wa_id}")
                        print(f"Appointment: {updated_referrer.appointment_date} at {updated_referrer.appointment_time}")
                        print(f"Treatment: {updated_referrer.treatment_type}")
                    else:
                        # Do not create a new record here; initial message should have created it
                        print(f"No existing referrer record for {wa_id}; skipping creation to avoid duplicates")
                    
            except Exception as e:
                print(f"Error processing appointment booking: {e}")
                import traceback
                traceback.print_exc()

        # 1️⃣ Onboarding prompt (only for first message)
        # if len(prior_messages) == 0:
        #     await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)

        # Address flow gating removed to allow other flows to proceed after "Provide Address"

        # 3️⃣ LEAD-TO-APPOINTMENT FLOW - handle Meta ad triggered flows FIRST (priority check)
        # Check for starting point messages before treatment flow to give lead appointment flow priority
        handled_text = False
        if message_type == "text" and body_text:
            # Quick check for lead appointment starting point patterns
            # Normalize Unicode characters for better matching
            try:
                import unicodedata
                body_text_normalized = unicodedata.normalize('NFKC', body_text)
                # Replace various apostrophe/quote characters with standard apostrophe (handle all Unicode variants)
                # U+2019 (right single quotation mark), U+2018 (left single quotation mark), U+02BC (modifier letter apostrophe)
                body_text_normalized = body_text_normalized.replace("'", "'")  # Right single quotation mark → standard apostrophe
                body_text_normalized = body_text_normalized.replace("'", "'")  # Left single quotation mark → standard apostrophe
                body_text_normalized = body_text_normalized.replace("'", "'")  # Modifier letter apostrophe → standard apostrophe
                body_text_normalized = body_text_normalized.replace("'", "'")  # Any other variants
                body_text_normalized = body_text_normalized.replace(""", '"').replace(""", '"')
            except Exception:
                # Fallback: replace common apostrophe variants
                body_text_normalized = body_text.replace("'", "'").replace("'", "'").replace("'", "'")
            
            normalized_check = ' '.join(body_text_normalized.lower().strip().rstrip('.').split())
            
            # Debug logging for server troubleshooting
            print(f"[lead_appointment_flow] DEBUG - Checking message: wa_id={wa_id}")
            print(f"[lead_appointment_flow] DEBUG - Original body_text (first 150 chars): '{body_text[:150]}'")
            print(f"[lead_appointment_flow] DEBUG - Normalized (first 150 chars): '{normalized_check[:150]}'")
            
            # Check for pattern match (more flexible)
            # Only match standard ad link messages for lead appointment flow
            # Location/clinic inquiry messages ("want to know more about services in...") should go to TREATMENT flow
            has_pattern = (
                "i saw your ad for oliva" in normalized_check 
                and "want to know more" in normalized_check
            )
            
            # Also check exact matches (but with normalized apostrophes)
            exact_matches = [
                "hi! i saw your ad for oliva's hair regrowth treatments and want to know more",
                "hi! i saw your ad for oliva's precision+ laser hair reduction and want to know more",
                "hi! i saw your ad for oliva's skin brightening treatments and want to know more",
                "hi! i saw your ad for oliva's acne & scar treatments and want to know more",
                "hi! i saw your ad for oliva's skin boosters and want to know more",
            ]
            # Normalize apostrophes in exact matches too
            normalized_exact_matches = [m.replace("'", "'").replace("'", "'") for m in exact_matches]
            
            is_exact_match = normalized_check in normalized_exact_matches
            is_lead_starting_point = has_pattern or is_exact_match
            
            print(f"[lead_appointment_flow] DEBUG - Pattern check: has_pattern={has_pattern}")
            print(f"[lead_appointment_flow] DEBUG - Exact match check: is_exact_match={is_exact_match}")
            print(f"[lead_appointment_flow] DEBUG - Final result: is_lead_starting_point={is_lead_starting_point}, wa_id={wa_id}")
            print(f"[lead_appointment_flow] DEBUG - Note: Location inquiry messages (like 'want to know more about services in...') route to TREATMENT flow")
            
            if is_lead_starting_point:
                # Restrict lead appointment flow to dedicated number only
                try:
                    from controllers.components.lead_appointment_flow.config import LEAD_APPOINTMENT_PHONE_ID, LEAD_APPOINTMENT_DISPLAY_LAST10  # type: ignore
                    phone_id_meta = (value or {}).get("metadata", {}).get("phone_number_id") if isinstance(value, dict) else None
                    display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") if isinstance(value, dict) else None
                    import re as _re
                    disp_digits = _re.sub(r"\D", "", (display_num or to_wa_id or ""))
                    lead_allowed = (str(phone_id_meta) == str(LEAD_APPOINTMENT_PHONE_ID)) or (disp_digits.endswith(str(LEAD_APPOINTMENT_DISPLAY_LAST10)))
                except Exception:
                    lead_allowed = False

                if not lead_allowed:
                    print(f"[lead_appointment_flow] DEBUG - Skipping lead flow: not dedicated number (pid={phone_id_meta}, disp={display_num})")
                else:
                    print(f"[lead_appointment_flow] DEBUG - ✅ Starting point detected on dedicated number! Running lead appointment flow...")
                    # Clear stale state to allow flow restart
                    try:
                        from controllers.state.memory import clear_flow_state_for_restart
                        clear_flow_state_for_restart(wa_id)
                        print(f"[lead_appointment_flow] DEBUG - Cleared stale state for new flow start: wa_id={wa_id}")
                    except Exception as e:
                        print(f"[lead_appointment_flow] WARNING - Could not clear stale state: {e}")
                    # Lead appointment flow has priority - skip treatment flow for these messages
                    try:
                        lead_result = await run_lead_appointment_flow(
                            db,
                            wa_id=wa_id,
                            message_type=message_type,
                            message_id=message_id,
                            from_wa_id=from_wa_id,
                            to_wa_id=to_wa_id,
                            body_text=body_text,
                            timestamp=timestamp,
                            customer=customer,
                            interactive=interactive,
                            i_type=i_type,
                        )
                        lead_status = (lead_result or {}).get("status")
                        print(f"[lead_appointment_flow] DEBUG - Lead flow result: status={lead_status}, result={lead_result}")
                        
                        if lead_status not in {"skipped", "error"}:
                            print(f"[lead_appointment_flow] DEBUG - ✅ Lead flow handled successfully, returning result")
                            return lead_result
                        else:
                            print(f"[lead_appointment_flow] DEBUG - ⚠️ Lead flow returned skipped/error: {lead_status}")
                        
                        handled_text = lead_status in {"auto_welcome_sent", "proceed_to_city_selection", "proceed_to_clinic_location", "proceed_to_time_slot", "waiting_for_custom_date", "callback_initiated", "lead_created_no_callback", "thank_you_sent", "week_list_sent", "day_list_sent", "time_slots_sent", "times_sent"}
                    except Exception as e:
                        print(f"[lead_appointment_flow] ERROR - Exception in lead appointment flow: {str(e)}")
                        import traceback
                        print(f"[lead_appointment_flow] ERROR - Traceback: {traceback.format_exc()}")
                        # Don't fail completely, let other flows try

        # 2️⃣ Ensure mr_welcome is sent FIRST on the dedicated number (one-time per user)
        # Only for the two allowed treatment flow numbers: 7617613030 and 8297882978
        try:
            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
            welcome_pid_env = os.getenv("WELCOME_PHONE_ID") or os.getenv("TREATMENT_FLOW_PHONE_ID")
            phone_id_meta = (value or {}).get("metadata", {}).get("phone_number_id") if isinstance(value, dict) else None
            
            # Check if this is an allowed phone number for treatment flow
            is_allowed_number = False
            if phone_id_meta and str(phone_id_meta) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                is_allowed_number = True
            else:
                # Also check by display phone number as fallback - compare last 10 digits
                try:
                    display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                    import re as _re
                    from marketing.whatsapp_numbers import WHATSAPP_NUMBERS
                    disp_digits = _re.sub(r"\D", "", display_num or "")
                    # Get last 10 digits of display number (phone number without country code)
                    disp_last10 = disp_digits[-10:] if len(disp_digits) >= 10 else disp_digits
                    
                    for pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                        cfg = WHATSAPP_NUMBERS.get(pid)
                        if cfg:
                            name_digits = _re.sub(r"\D", "", (cfg.get("name") or ""))
                            # Get last 10 digits of stored phone number
                            name_last10 = name_digits[-10:] if len(name_digits) >= 10 else name_digits
                            # Match if last 10 digits are the same
                            if name_last10 and disp_last10 and name_last10 == disp_last10:
                                is_allowed_number = True
                                break
                except Exception:
                    pass
            
            already_welcomed = bool((appointment_state.get(wa_id) or {}).get("mr_welcome_sent"))
            # Only send mr_welcome for allowed numbers and on the user's first inbound text (unless already sent)
            should_send_welcome = is_allowed_number and not already_welcomed
            if should_send_welcome:
                welcome_result = await run_mr_welcome_number_flow(
                    db,
                    wa_id=wa_id,
                    to_wa_id=to_wa_id,
                    message_id=message_id,
                    message_type=message_type,
                    timestamp=timestamp,
                    customer=customer,
                    value=value,
                )
                if (welcome_result or {}).get("status") == "welcome_sent":
                    st = appointment_state.get(wa_id) or {}
                    st["mr_welcome_sent"] = True
                    appointment_state[wa_id] = st
                    return welcome_result
        except Exception:
            pass

        # 3️⃣ AUTO WELCOME VALIDATION - extracted to component function
        if not handled_text and message_type == "text":
            result = await run_treament_flow(
                db,
                message_type=message_type,
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                body_text=body_text,
                timestamp=timestamp,
                customer=customer,
                wa_id=wa_id,
                value=value,
                sender_name=sender_name,
            )
            # DEBUG: log treatment flow result
            try:
                print(f"[ws_webhook] DEBUG - treatment flow result: {result}")
            except Exception:
                pass
            status_val = (result or {}).get("status")
            if status_val in {"welcome_sent", "welcome_failed"}:
                return result
            # If skipped, bootstrap Treatment Flow via dedicated number (mr_treatment)
            # BUT do not bootstrap while we're already in the name/phone correction path
            # AND only if the inbound number is one of the allowed Treatment Flow numbers
            if status_val == "skipped":
                # Gate: allow bootstrap only for the two approved numbers
                try:
                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS, WHATSAPP_NUMBERS as _MAP
                    import re as _re
                    phone_id_meta2 = (value or {}).get("metadata", {}).get("phone_number_id") if isinstance(value, dict) else None
                    allowed_inbound = False
                    if phone_id_meta2 and str(phone_id_meta2) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                        allowed_inbound = True
                    else:
                        disp_num2 = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                        disp_digits2 = _re.sub(r"\D", "", disp_num2 or "")
                        disp_last10_2 = disp_digits2[-10:] if len(disp_digits2) >= 10 else disp_digits2
                        for _pid, _cfg in (_MAP or {}).items():
                            if _pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                name_digits2 = _re.sub(r"\D", "", (_cfg.get("name") or ""))
                                name_last10_2 = name_digits2[-10:] if len(name_digits2) >= 10 else name_digits2
                                if name_last10_2 and disp_last10_2 and name_last10_2 == disp_last10_2:
                                    allowed_inbound = True
                                    break
                except Exception:
                    allowed_inbound = False

                if not allowed_inbound:
                    try:
                        print(f"[ws_webhook] DEBUG - Skip bootstrap: inbound number not in allowed list (to_wa_id={to_wa_id})")
                    except Exception:
                        pass
                    return {"status": "skipped", "message_id": message_id}
                # Skip bootstrap entirely to prevent duplicate/conflicting messages
            handled_text = status_val in {"handled"}

        # 3️⃣ LEAD-TO-APPOINTMENT FLOW - handle other lead appointment triggers
        if not handled_text:
            # Guard: do not route treatment city selections into lead flow
            try:
                if message_type == "interactive" and i_type in {"list_reply", "button_reply"}:
                    rid_guard = None
                    try:
                        rid_guard = (interactive.get("list_reply", {}) or {}).get("id") if i_type == "list_reply" else (interactive.get("button_reply", {}) or {}).get("id")
                    except Exception:
                        rid_guard = None
                    rid_norm = (rid_guard or "").strip().lower()
                    if rid_norm.startswith("city_"):
                        # Confirm this came on a treatment number
                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS, WHATSAPP_NUMBERS as _MAP
                        import re as _re
                        pid_meta_g = (value or {}).get("metadata", {}).get("phone_number_id") if isinstance(value, dict) else None
                        allowed_num = False
                        if pid_meta_g and str(pid_meta_g) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                            allowed_num = True
                        else:
                            disp_num_g = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                            disp_digits_g = _re.sub(r"\D", "", disp_num_g or "")
                            disp_last10_g = disp_digits_g[-10:] if len(disp_digits_g) >= 10 else disp_digits_g
                            for _pid, _cfg in (_MAP or {}).items():
                                if _pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                    name_digits_g = _re.sub(r"\D", "", (_cfg.get("name") or ""))
                                    name_last10_g = name_digits_g[-10:] if len(name_digits_g) >= 10 else name_digits_g
                                    if name_last10_g and disp_last10_g and name_last10_g == disp_last10_g:
                                        allowed_num = True
                                        break
                        print(f"[ws_webhook] DEBUG - City selection routing check: rid={rid_norm} pid={pid_meta_g} disp={disp_num_g} allowed={allowed_num}")
                        if allowed_num:
                            print(f"[ws_webhook] DEBUG - Routing treatment city reply (rid={rid_norm}) to marketing handler")
                            try:
                                from marketing.city_selection import handle_city_selection  # type: ignore
                                city_result = await handle_city_selection(
                                    db,
                                    wa_id=wa_id,
                                    reply_id=rid_guard,
                                    customer=customer
                                )
                                city_status = (city_result or {}).get("status")
                                print(f"[ws_webhook] DEBUG - Treatment city handler returned: status={city_status}")
                                if city_status not in {"skipped", "error"}:
                                    return city_result
                            except Exception as e:
                                print(f"[ws_webhook] ERROR - Failed to handle treatment city: {e}")
                                import traceback
                                traceback.print_exc()
                            return {"status": "treatment_city_handled"}
                        else:
                            print(f"[ws_webhook] DEBUG - City selection NOT on treatment number, routing to lead flow")
            except Exception as e:
                print(f"[ws_webhook] WARNING - City routing guard exception: {e}")
                pass
            print(f"[ws_webhook] DEBUG - Attempting lead appointment flow for wa_id={wa_id} message_type={message_type}")
            lead_result = await run_lead_appointment_flow(
                db,
                wa_id=wa_id,
                message_type=message_type,
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                body_text=body_text,
                timestamp=timestamp,
                customer=customer,
                interactive=interactive,
                i_type=i_type,
                phone_number_id=phone_number_id_str,
            )
            lead_status = (lead_result or {}).get("status")
            print(f"[ws_webhook] DEBUG - Lead appointment flow returned: status={lead_status}")
            if lead_status not in {"skipped", "error"}:
                print(f"[ws_webhook] DEBUG - Lead appointment flow handled successfully, returning")
                return lead_result
            handled_text = lead_status in {"auto_welcome_sent", "proceed_to_city_selection", "proceed_to_clinic_location", "proceed_to_time_slot", "waiting_for_custom_date", "callback_initiated", "lead_created_no_callback", "thank_you_sent", "week_list_sent", "day_list_sent", "time_slots_sent", "times_sent"}
            print(f"[ws_webhook] DEBUG - After lead flow: handled_text={handled_text}")

        # Manual date-time fallback parsing before other generic text handling
        if message_type == "text" and not handled_text:
            try:
                # Pattern: DD-MM-YYYY, HH:MM AM/PM (also supports / as separator)
                m_dt = re.search(r"\b(\d{1,2})[\-\/](\d{1,2})[\-\/]?(\d{2,4})\b\s*,?\s*(\d{1,2}):(\d{2})\s*([APap][Mm])", body_text)
                m_d = re.search(r"\b(\d{1,2})[\-\/]((\d{1,2}))[\-\/]?(\d{2,4})\b", body_text)
                if m_dt:
                    dd, mm, yyyy, hh, mins, ampm = m_dt.groups()
                    yyyy = yyyy if len(yyyy) == 4 else ("20" + yyyy)
                    date_iso = f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
                    time_label = f"{int(hh):02d}:{int(mins):02d} {ampm.upper()}"
                    appointment_state[wa_id] = {"date": date_iso}
                    await _confirm_appointment(wa_id, db, date_iso, time_label)
                    return {"status": "appointment_captured", "message_id": message_id}
                elif m_d:
                    dd, mm, _, yyyy = m_d.groups()
                    yyyy = yyyy if len(yyyy) == 4 else ("20" + yyyy)
                    date_iso = f"{int(yyyy):04d}-{int(mm):02d}-{int(dd):02d}"
                    appointment_state[wa_id] = {"date": date_iso}
                    await send_message_to_waid(wa_id, f"✅ Date noted: {date_iso}", db)
                    await send_time_buttons(wa_id, db)
                    return {"status": "date_selected", "message_id": message_id}
            except Exception:
                pass

        # Handle dummy payment request
        if message_type == "text" and body_text:
            text_lower = body_text.lower().strip()
            if "dummy payment" in text_lower or "test payment" in text_lower:
                try:
                    from services.dummy_payment_service import DummyPaymentService
                    dummy_service = DummyPaymentService(db)
                    
                    # Create dummy payment link
                    result = await dummy_service.create_dummy_payment_link(
                        wa_id=wa_id,
                        customer_name=getattr(customer, "name", None)
                    )
                    
                    if result.get("success"):
                        print(f"[dummy_payment] Dummy payment link created: {result.get('payment_url')}")
                    else:
                        print(f"[dummy_payment] Failed to create dummy payment: {result.get('error')}")
                        await send_message_to_waid(wa_id, "❌ Failed to create test payment link.", db)
                    
                    return {"status": "dummy_payment_sent", "message_id": message_id}
                except Exception as e:
                    print(f"[dummy_payment] Error: {e}")
                    await send_message_to_waid(wa_id, "❌ Error creating test payment link.", db)
                    return {"status": "dummy_payment_failed", "message_id": message_id}

        # 4️⃣ Regular text messages - ALWAYS save to database regardless of handling
        if message_type == "text":
            # Check if already saved to avoid duplicates
            existing_msg = db.query(Message).filter(Message.message_id == message_id).first()
            if not existing_msg:
                inbound_text_msg = MessageCreate(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    to_wa_id=to_wa_id,
                    type="text",
                    body=body_text,
                    timestamp=timestamp,
                    customer_id=customer.id
                )
                message_service.create_message(db, inbound_text_msg)
                db.commit()  # Explicitly commit the transaction
                
                # Only mark customer as replied if they have previous OUTBOUND messages from us
                # AND the follow-up wasn't just scheduled (to avoid clearing follow-ups for initial messages)
                try:
                    from services.followup_service import mark_customer_replied as _mark_replied
                    from models.models import Customer
                    from datetime import datetime as dt, timedelta
                    
                    # Refresh customer object to get latest state
                    db.refresh(customer)
                    
                    # Check if follow-up was just scheduled - don't clear if so
                    if customer.next_followup_time:
                        # We look at last_message_type to see if it was just set by treatment flow
                        if customer.last_message_type and "welcome" in customer.last_message_type.lower():
                            # Follow-up was just scheduled by treatment flow in response to INITIAL message
                            # This is ALWAYS an initial message - we just sent the welcome message!
                            # NEVER clear the follow-up for initial messages in welcome flow
                            # The whole point is to follow up if they don't respond to our welcome message
                            print(f"[ws_webhook] DEBUG - Customer {wa_id} initial message in welcome flow - PRESERVING follow-up scheduled at {customer.next_followup_time} (this is the message that triggered the welcome)")
                        else:
                            # Not a welcome flow - use normal logic
                            our_phone = os.getenv("WHATSAPP_PHONE_ID", "917729992376")
                            has_outbound_before = db.query(Message).filter(
                                Message.customer_id == customer.id,
                                Message.from_wa_id == our_phone,
                                Message.timestamp < timestamp
                            ).first() is not None
                            
                            if has_outbound_before:
                                _mark_replied(db, customer_id=customer.id)
                                print(f"[ws_webhook] DEBUG - Customer {wa_id} replied after our message - cleared follow-up")
                            else:
                                print(f"[ws_webhook] DEBUG - Customer {wa_id} initial message - preserving scheduled follow-up")
                    else:
                        # No follow-up scheduled - no need to clear
                        print(f"[ws_webhook] DEBUG - Customer {wa_id} - no follow-up scheduled, nothing to clear")
                except Exception as e:
                    print(f"[ws_webhook] WARNING - Could not check if customer replied: {e}")
                    import traceback
                    traceback.print_exc()
                    # If error, default to NOT clearing follow-up for safety
                    pass
                print(f"[ws_webhook] DEBUG - Inbound text message saved to database:")
                print(f"  - Message ID: {message_id}")
                print(f"  - From: {from_wa_id}")
                print(f"  - To: {to_wa_id}")
                print(f"  - Type: text")
                print(f"  - Body: {body_text}")
                print(f"  - Timestamp: {timestamp}")
                print(f"  - Customer ID: {customer.id}")
            
            # If we are waiting for user details (after confirm_no in treatment flow), handle now
            try:
                from controllers.web_socket import lead_appointment_state as _lead_state  # type: ignore
                waiting_details = ((_lead_state.get(wa_id) or {}).get("waiting_for_user_details"))
            except Exception:
                waiting_details = False

            if waiting_details:
                try:
                    from controllers.components.lead_appointment_flow.user_details import handle_user_details_input  # type: ignore
                    result = await handle_user_details_input(db=db, wa_id=wa_id, details_text=body_text, customer=customer)
                    return {"status": "user_details_handled", **result}
                except Exception:
                    pass

            # Always broadcast to WebSocket (even if already saved)
            if not handled_text:  # Only broadcast if not already handled by treatment flow
                # Determine flow context for broadcast metadata
                flow_context = "treatment" if is_treatment_flow_number else ("lead_appointment" if is_lead_appointment_number else "unknown")
                await manager.broadcast({
                    "from": wa_id,  # Customer's WA ID
                    "to": to_wa_id,  # Business number
                    "type": "text",
                    "message": body_text,
                    "timestamp": timestamp.isoformat(),
                    "meta": {
                        "flow": flow_context,
                        "action": "customer_message"
                    }
                })

            # Catalog link is sent only on explicit button clicks; no text keyword trigger

        # 4️⃣ Hi/Hello auto-template (only if treatment flow didn't already handle)
        if not handled_text:
            welcome_result = await run_welcome_flow(
                db,
                message_type=message_type,
                body_text=body_text,
                wa_id=wa_id,
                to_wa_id=to_wa_id,
                sender_name=sender_name,
                customer=customer,
            )
            # no early return needed; this is an optional greeting handler

        # Send onboarding prompt on very first message from this WA ID
        # if len(prior_messages) == 0:
        #     await send_message_to_waid(wa_id, 'Type "Hi" or "Hello"', db)
      


        if message_type == "order":
            order = message["order"]
            order_items = [
                OrderItemCreate(
                    product_retailer_id=prod["product_retailer_id"],
                    quantity=prod["quantity"],
                    item_price=prod.get("item_price"),
                    currency=prod.get("currency")
                ) for prod in order["product_items"]
            ]

            # Check if this order addition is happening after a modify order action
            # by checking if the latest order has modification_started_at set
            is_modification = False
            try:
                # Use a separate session to avoid transaction conflicts
                from database.db import SessionLocal
                temp_db = SessionLocal()
                try:
                    latest_order = (
                        temp_db.query(order_service.Order)
                        .filter(order_service.Order.customer_id == customer.id)
                        .order_by(order_service.Order.timestamp.desc())
                        .first()
                    )
                    if latest_order and latest_order.modification_started_at:
                        is_modification = True
                finally:
                    temp_db.close()
            except Exception as e:
                print(f"[webhook] Error checking modification status: {e}")
                # Continue without modification flag if check fails

            # Merge into latest open order (if any); else create a new one
            try:
                order_obj = order_service.merge_or_create_order(
                    db,
                    customer_id=customer.id,
                    catalog_id=order.get("catalog_id"),
                    timestamp=timestamp,
                    items=order_items,
                    is_modification=is_modification,
                )
                print(f"[webhook] Order processed successfully: {order_obj.id}")
            except Exception as e:
                print(f"[webhook] Error processing order: {e}")
                # Rollback and try to continue
                db.rollback()
                return {"status": "failed", "error": f"Order processing failed: {str(e)}"}

            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "order",
                "catalog_id": order["catalog_id"],
                "products": order["product_items"],
                "timestamp": timestamp.isoformat(),
            })

            # After cart selection, ask the user to Modify / Cancel / Proceed
            try:
                from controllers.components.products_flow import send_cart_next_actions  # type: ignore
                await send_cart_next_actions(db, wa_id=wa_id)
            except Exception as e:
                print(f"[webhook] Error sending cart actions: {e}")
                # As a fallback, keep legacy behavior of sending address flow directly
                try:
                    await _send_address_flow_directly(wa_id, db, customer_id=customer.id)
                except Exception as fallback_error:
                    print(f"[webhook] Fallback address flow also failed: {fallback_error}")
                    await send_message_to_waid(wa_id, "✅ Items added to cart! Please proceed with checkout.", db)
        elif message_type == "location":
            location = message["location"]
            location_name = location.get("name", "")
            location_address = location.get("address", "")

            # convert to float safely
            latitude = float(location["latitude"]) if "latitude" in location else None
            longitude = float(location["longitude"]) if "longitude" in location else None

            # body fallback
            if location_name or location_address:
                location_body = ", ".join(filter(None, [location_name, location_address]))
            else:
                location_body = f"Shared Location - Lat: {latitude}, Lng: {longitude}"

            # NEW: Check if this is part of address collection
            try:
                from services.address_collection_service import AddressCollectionService
                address_service = AddressCollectionService(db)
                result = await address_service.handle_location_message(
                    wa_id=wa_id,
                    latitude=latitude,
                    longitude=longitude,
                    location_name=location_name,
                    location_address=location_address
                )
                
                if result["success"]:
                    # Address collection handled successfully
                    message_data = MessageCreate(
                        message_id=message_id,
                        from_wa_id=from_wa_id,
                        to_wa_id=to_wa_id,
                        type="location",
                        body=location_body,
                        timestamp=timestamp,
                        customer_id=customer.id,
                        latitude=latitude,
                        longitude=longitude,
                    )
                    message_service.create_message(db, message_data)
                    db.commit()  # Explicitly commit the transaction
                    
                    await manager.broadcast({
                        "from": from_wa_id,
                        "to": to_wa_id,
                        "type": "location",
                        "latitude": latitude,
                        "longitude": longitude,
                        "timestamp": timestamp.isoformat(),
                    })
                    return {"status": "address_collected", "message_id": message_id}
                else:
                    # Fallback to old location handling
                    pass
            except Exception as e:
                print(f"Address collection location handling failed: {e}")
                # Fallback to old location handling

            # OLD LOCATION HANDLING (fallback)
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="location",
                body=location_body,
                timestamp=timestamp,
                customer_id=customer.id,
                latitude=latitude,
                longitude=longitude,
            )
            message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction

            broadcast_payload = {
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "location",
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": timestamp.isoformat()
            }

            if location_name:
                broadcast_payload["name"] = location_name
            if location_address:
                broadcast_payload["address"] = location_address

            await manager.broadcast(broadcast_payload)

            return {"status": "success", "message_id": message_id}

        elif message_type == "image":
            image = message["image"]

            media_id = image.get("id")
            caption = image.get("caption", "")
            mime_type = image.get("mime_type", "")
            filename = image.get("filename", "")

            # Save message in DB
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="image",
                body=caption or "[Image]",
                timestamp=timestamp,
                customer_id=customer.id,
                media_id=media_id,
                caption=caption,
                filename=filename,
                mime_type=mime_type,
            )
            new_msg = message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction

            # Broadcast to WebSocket clients
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "image",
                "media_id": media_id,
                "caption": caption,
                "filename": filename,
                "mime_type": mime_type,
                "timestamp": timestamp.isoformat(),
            })

            return {"status": "success", "message_id": message_id}
        elif message_type == "button":
            # Template button reply (WhatsApp sets type = "button" for template quick replies)
            btn = message.get("button", {})
            btn_text = btn.get("text", "")
            btn_id = btn.get("payload") or btn.get("id") or ""

            # Check if this is actually a flow submission disguised as a button
            # Look for flow-related data in the message
            if "flow" in str(message).lower() or "nfm" in str(message).lower():
                print(f"[ws_webhook] DEBUG - Detected flow submission in button message: {message}")
                # Process as flow submission instead of button
                try:
                    # Try to extract flow data from the message
                    flow_data = message.get("flow", {}) or message.get("nfm_reply", {})
                    if flow_data:
                        print(f"[ws_webhook] DEBUG - Processing flow data from button message: {flow_data}")
                        # Process the flow submission
                        result = await run_interactive_type(
                            db,
                            message=message,
                            interactive={"type": "nfm_reply", "nfm_reply": flow_data},
                            i_type="nfm_reply",
                            timestamp=timestamp,
                            message_id=message_id,
                            from_wa_id=from_wa_id,
                            to_wa_id=to_wa_id,
                            wa_id=wa_id,
                            customer=customer,
                        )
                        if result.get("status") != "skipped":
                            return result
                except Exception as e:
                    print(f"[ws_webhook] DEBUG - Failed to process flow from button message: {e}")

            reply_text = btn_text or btn_id or "[Button Reply]"
            msg_button = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="button",
                body=reply_text,
                timestamp=timestamp,
                customer_id=customer.id,
            )
            message_service.create_message(db, msg_button)
            db.commit()  # Explicitly commit the transaction
            
            # Optionally broadcast button click for frontend display, but avoid noise for main flows
            noisy_btn_id = (btn_id or "").lower()
            if noisy_btn_id not in {"buy_products", "book_appointment", "request_callback"}:
                await manager.broadcast({
                    "from": from_wa_id,
                    "to": to_wa_id,
                    "type": "text",
                    "message": f"🔘 {reply_text}",
                    "timestamp": timestamp.isoformat(),
                })

            # Handle different button types
            choice_text = (reply_text or "").strip().lower()

            # Buy Products from template button → trigger catalog flow immediately
            btn_id_norm = (btn_id or "").strip().lower()
            if btn_id_norm in {"buy_products", "buy product", "buy products"} or choice_text == "buy products":
                try:
                    await trigger_buy_products_from_welcome(db, wa_id=wa_id)
                except Exception:
                    pass
                return {"status": "success", "message_id": message_id}  # INSERTED: hard return (no more handlers)

            # NEW: Delegate Skin/Hair/Body and related list selections to component flow
            flow_result = await run_treatment_buttons_flow(
                db,
                wa_id=wa_id,
                to_wa_id=to_wa_id,
                message_id=message_id,
                btn_id=btn_id,
                btn_text=btn_text,
                btn_payload=(btn.get("payload") if isinstance(btn, dict) else None),
            )
            if (flow_result or {}).get("status") in {"list_sent", "hair_template_sent", "body_template_sent", "next_actions_sent"}:
                return flow_result

            # Handle template button clicks from oliva_meta_ad template
            # Map template button payloads to lead appointment flow IDs
            template_btn_mapping = {
                "yes, book now": "yes_book_appointment",
                "yes book now": "yes_book_appointment",
                "not now": "not_now",
                "not now,": "not_now",
            }
            
            # Check if this is a template button from oliva_meta_ad
            normalized_payload = (btn_text or "").strip().lower()
            mapped_id = template_btn_mapping.get(normalized_payload)
            
            if mapped_id:
                print(f"[ws_webhook] DEBUG - Template button detected: '{btn_text}' → mapped to '{mapped_id}'")
                
                # Process as lead appointment flow interactive response
                mock_interactive = {
                    "button_reply": {
                        "id": mapped_id,
                        "title": btn_text
                    }
                }
                
                # Check if user is in lead appointment flow
                try:
                    from controllers.web_socket import lead_appointment_state
                    is_in_lead_flow = wa_id in lead_appointment_state and bool(lead_appointment_state[wa_id])
                    
                    # Also check if template button (first interaction)
                    if mapped_id in {"yes_book_appointment", "not_now"}:
                        is_in_lead_flow = True
                    
                    if is_in_lead_flow or mapped_id in {"yes_book_appointment", "not_now"}:
                        # Restrict lead appointment flow to dedicated number only
                        try:
                            from controllers.components.lead_appointment_flow.config import LEAD_APPOINTMENT_PHONE_ID, LEAD_APPOINTMENT_DISPLAY_LAST10  # type: ignore
                            phone_id_meta = (value or {}).get("metadata", {}).get("phone_number_id") if isinstance(value, dict) else None
                            display_num = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") if isinstance(value, dict) else None
                            import re as _re
                            disp_digits = _re.sub(r"\D", "", (display_num or to_wa_id or ""))
                            lead_allowed = (str(phone_id_meta) == str(LEAD_APPOINTMENT_PHONE_ID)) or (disp_digits.endswith(str(LEAD_APPOINTMENT_DISPLAY_LAST10)))
                        except Exception:
                            lead_allowed = False

                        if not lead_allowed:
                            print(f"[ws_webhook] DEBUG - Skipping lead flow (template button) on non-dedicated number (pid={phone_id_meta}, disp={display_num})")
                            raise Exception("not_lead_number")

                        print(f"[ws_webhook] DEBUG - Routing to lead appointment flow for '{mapped_id}' on dedicated number")
                        lead_result = await run_lead_appointment_flow(
                            db=db,
                            wa_id=wa_id,
                            message_type="interactive",
                            message_id=message_id,
                            from_wa_id=from_wa_id,
                            to_wa_id=to_wa_id,
                            body_text=None,
                            timestamp=timestamp,
                            customer=customer,
                            interactive=mock_interactive,
                            i_type="button_reply",
                        )
                        if lead_result.get("status") not in {"skipped", "error"}:
                            print(f"[ws_webhook] DEBUG - Lead appointment flow handled: {lead_result.get('status')}")
                            return lead_result
                except Exception as e:
                    print(f"[ws_webhook] WARNING - Failed to process template button in lead flow: {e}")

            # Delegate appointment button flows (book, callback, time)
            from controllers.components.treament_flow import run_appointment_buttons_flow  # local import to avoid cycles
            appt_result_ctrl = await run_appointment_buttons_flow(
                db,
                wa_id=wa_id,
                btn_id=btn_id,
                btn_text=btn_text,
                btn_payload=(btn.get("payload") if isinstance(btn, dict) else None),
            )
            if (appt_result_ctrl or {}).get("status") in {"date_list_sent", "callback_ack", "appointment_captured", "need_date_first"}:
                return appt_result_ctrl

            # Address collection buttons (legacy guidance removed); allow flows to proceed without interception

            return {"status": "success", "message_id": message_id}

        elif message_type == "interactive":
            # interactive and i_type already initialized above
            print(f"[ws_webhook] DEBUG - Interactive type: {i_type}")
            if i_type == "flow":
                flow_response = interactive.get("flow_response", {})
                flow_id = flow_response.get("flow_id", "")
                print(f"[ws_webhook] DEBUG - Flow ID: {flow_id}")
                print(f"[ws_webhook] DEBUG - Flow payload: {flow_response.get('flow_action_payload', {})}")
            elif i_type == "nfm_reply":
                # Handle native flow message (new format)
                nfm_reply = interactive.get("nfm_reply", {})
                print(f"[ws_webhook] DEBUG - NFM Reply: {nfm_reply}")
                
                # Enhanced logging for debugging
                response_json = nfm_reply.get("response_json", "{}")
                print(f"[ws_webhook] DEBUG - Raw response_json: {response_json}")
                print(f"[ws_webhook] DEBUG - Response JSON length: {len(response_json)}")
                
                # Parse the response_json to extract flow data
                try:
                    response_data = json.loads(response_json)
                    print(f"[ws_webhook] DEBUG - Parsed NFM data: {response_data}")
                    print(f"[ws_webhook] DEBUG - Parsed data keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")

                    # Check if we got template variables instead of actual values
                    has_template_vars = any("{{" in str(v) and "}}" in str(v) for v in response_data.values())
                    if has_template_vars:
                        print(f"[ws_webhook] WARNING - Received template variables instead of actual values: {response_data}")
                        print(f"[ws_webhook] INFO - Processing template placeholders to extract actual values")
                        
                        # Process template placeholders and extract actual values
                        processed_data = {}
                        for key, value in response_data.items():
                            if isinstance(value, str) and "{{" in value and "}}" in value:
                                # Extract the placeholder name (e.g., "{{name}}" -> "name")
                                placeholder_match = re.search(r'\{\{([^}]+)\}\}', value)
                                if placeholder_match:
                                    placeholder_name = placeholder_match.group(1).strip()
                                    # Try to get actual value from customer data or use fallback
                                    if hasattr(customer, 'name') and customer.name and placeholder_name == 'name':
                                        processed_data[key] = customer.name
                                    elif hasattr(customer, 'wa_id') and placeholder_name == 'phone':
                                        # Use wa_id as phone fallback (remove country code if present)
                                        phone = customer.wa_id.replace('91', '') if customer.wa_id.startswith('91') else customer.wa_id
                                        processed_data[key] = phone
                                    else:
                                        # Use placeholder name as fallback value
                                        processed_data[key] = placeholder_name
                                else:
                                    processed_data[key] = value
                            else:
                                processed_data[key] = value
                        
                        print(f"[ws_webhook] INFO - Processed data from placeholders: {processed_data}")
                        response_data = processed_data

                    # Process the flow response data directly
                    # The flow fields are defined in Meta's Flow Builder, not here
                    print(f"[ws_webhook] DEBUG - Flow response data: {response_data}")
                    print(f"[ws_webhook] INFO - Flow fields received: {list(response_data.keys())}")
                    
                    # Debug each field individually
                    for key, value in response_data.items():
                        print(f"[ws_webhook] DEBUG - Field '{key}': '{value}' (type: {type(value)})")
                    
                    # No field mapping needed - use the data as received from Meta
                    # Meta's Flow Builder defines the field names and structure

                    # Validate that we have actual data
                    if not response_data or (isinstance(response_data, dict) and not any(response_data.values())):
                        print(f"[ws_webhook] WARNING - Empty or invalid response data: {response_data}")
                        await send_message_to_waid(wa_id, "❌ No data received from the form. Please try again.", db)
                        return {"status": "empty_form_data", "message_id": message_id}

                    # Convert nfm_reply to flow_response format for compatibility
                    interactive["type"] = "flow"
                    interactive["flow_response"] = {
                        "flow_id": "1314521433687006",  # Default address flow ID
                        "flow_cta": "Submit",
                        "flow_action_payload": response_data,  # Use data as received from Meta
                    }
                    i_type = "flow"  # Update type for processing
                    print(f"[ws_webhook] DEBUG - Converted to flow format, processing as flow")

                except json.JSONDecodeError as e:
                    print(f"[ws_webhook] ERROR - Invalid JSON in NFM response: {e}")
                    print(f"[ws_webhook] ERROR - Raw response_json: {response_json}")
                    await send_message_to_waid(wa_id, "❌ There was an error processing your form. Please try again.", db)
                    return {"status": "json_parse_error", "message_id": message_id}
                except Exception as e:
                    print(f"[ws_webhook] ERROR - Failed to parse NFM response: {e}")
                    print(f"[ws_webhook] ERROR - Exception type: {type(e).__name__}")
                    await send_message_to_waid(wa_id, "❌ There was an error processing your form. Please try again.", db)
                    return {"status": "parse_error", "message_id": message_id}
            # Delegate interactive handling to component
            print(f"[ws_webhook] DEBUG - Routing to interactive_type handler: i_type={i_type} wa_id={wa_id} to_wa_id={to_wa_id}")
            result_interactive = await run_interactive_type(
                db,
                message=message,
                interactive=interactive,
                i_type=i_type,
                timestamp=timestamp,
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                wa_id=wa_id,
                customer=customer,
            )
            interactive_status = (result_interactive or {}).get("status")
            print(f"[ws_webhook] DEBUG - Interactive handler returned: status={interactive_status}")
            if interactive_status != "skipped":
                print(f"[ws_webhook] DEBUG - Interactive handler processed message, returning")
                return result_interactive
            
            # Handle other interactive types (buttons, lists)
            try:
                if i_type == "button_reply":
                    title = interactive.get("button_reply", {}).get("title")
                    reply_id = interactive.get("button_reply", {}).get("id")
                elif i_type == "list_reply":
                    title = interactive.get("list_reply", {}).get("title")
                    reply_id = interactive.get("list_reply", {}).get("id")
                else:
                    title = None
                    reply_id = None
            except Exception:
                title = None
                reply_id = None

            # NEW: Immediately persist and broadcast ANY interactive reply before branching,
            # so UI always shows the user's selection even if we return early later.
            interactive_broadcasted = False
            try:
                if i_type in {"button_reply", "list_reply"}:
                    # Clear any pending interactive since user responded
                    try:
                        st_clear = appointment_state.get(wa_id) or {}
                        st_clear.pop("pending_interactive", None)
                        appointment_state[wa_id] = st_clear
                    except Exception:
                        pass
                    reply_text_any = (title or reply_id or "[Interactive Reply]")
                    msg_interactive_any = MessageCreate(
                        message_id=message_id,
                        from_wa_id=from_wa_id,
                        to_wa_id=to_wa_id,
                        type="interactive",
                        body=reply_text_any,
                        timestamp=timestamp,
                        customer_id=customer.id,
                    )
                    message_service.create_message(db, msg_interactive_any)
                    db.commit()  # Explicitly commit the transaction
                    # Determine flow context for broadcast metadata
                    flow_context = "treatment" if is_treatment_flow_number else ("lead_appointment" if is_lead_appointment_number else "unknown")
                    await manager.broadcast({
                        "from": wa_id,  # Customer's WA ID
                        "to": to_wa_id,  # Business number
                        "type": "interactive",
                        "message": reply_text_any,
                        "timestamp": timestamp.isoformat(),
                        "meta": {
                            "flow": flow_context,
                            "action": "customer_message",
                            "interactive_type": i_type
                        }
                    })
                    interactive_broadcasted = True
                    
                    # Mark customer as replied and reset follow-up timer for ANY interactive response
                    # This ensures follow-up timer resets from user's last interaction (button/list click)
                    try:
                        from services.followup_service import mark_customer_replied as _mark_replied
                        db.refresh(customer)  # Refresh to get latest state
                        _mark_replied(db, customer_id=customer.id, reset_followup_timer=True)
                        print(f"[ws_webhook] DEBUG - Customer {wa_id} interactive reply ({i_type}) - reset follow-up timer from last interaction")
                    except Exception as e:
                        print(f"[ws_webhook] WARNING - Could not mark customer replied for interactive message: {e}")
                        import traceback
                        traceback.print_exc()
            except Exception:
                pass

            # Step 2 → 3: Skin/Hair/Body handling is centralized in controllers.components.treament_flow
            # Avoid duplicate sends here (was causing duplicate skin_treat_flow and lists)
            try:
                if False and i_type == "button_reply" and (reply_id or "").lower() in {"skin", "hair", "body"}:
                    token_entry2 = get_latest_token(db)
                    if token_entry2 and token_entry2.token:
                        access_token2 = token_entry2.token
                        headers2 = {"Authorization": f"Bearer {access_token2}", "Content-Type": "application/json"}
                        phone_id2 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

                        topic = (reply_id or "").lower()
                        # If SKIN selected, trigger template skin_treat_flow (no params assumed)
                        if topic == "skin":
                            try:
                                from controllers.auto_welcome_controller import _send_template
                                lang_code_skin = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                                resp_skin = _send_template(
                                    wa_id=wa_id,
                                    template_name="skin_treat_flow",
                                    access_token=token_entry2.token,
                                    phone_id=phone_id2,
                                    components=None,
                                    lang_code=lang_code_skin
                                )
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template" if resp_skin.status_code == 200 else "template_error",
                                        "message": "skin_treat_flow sent" if resp_skin.status_code == 200 else "skin_treat_flow failed",
                                        **({"status_code": resp_skin.status_code} if resp_skin.status_code != 200 else {}),
                                        **({"error": (resp_skin.text[:500] if isinstance(resp_skin.text, str) else str(resp_skin.text))} if resp_skin.status_code != 200 else {}),
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                            except Exception as e:
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template_error",
                                        "message": f"skin_treat_flow exception: {str(e)[:120]}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                        # If HAIR selected, trigger template hair_treat_flow (no params assumed) and STOP
                        elif topic == "hair":
                            try:
                                from controllers.auto_welcome_controller import _send_template
                                lang_code_hair = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                                resp_hair = _send_template(
                                    wa_id=wa_id,
                                    template_name="hair_treat_flow",
                                    access_token=token_entry2.token,
                                    phone_id=phone_id2,
                                    components=None,
                                    lang_code=lang_code_hair
                                )
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template" if resp_hair.status_code == 200 else "template_error",
                                        "message": "hair_treat_flow sent" if resp_hair.status_code == 200 else "hair_treat_flow failed",
                                        **({"status_code": resp_hair.status_code} if resp_hair.status_code != 200 else {}),
                                        **({"error": (resp_hair.text[:500] if isinstance(resp_hair.text, str) else str(resp_hair.text))} if resp_hair.status_code != 200 else {}),
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                                # Do not send any further lists or flows for hair; exit early
                                return {"status": "hair_template_sent", "message_id": message_id}
                            except Exception as e:
                                try:
                                    await manager.broadcast({
                                        "from": to_wa_id,
                                        "to": wa_id,
                                        "type": "template_error",
                                        "message": f"hair_treat_flow exception: {str(e)[:120]}",
                                        "timestamp": datetime.now().isoformat()
                                    })
                                except Exception:
                                    pass
                        def list_rows(items):
                            return [{"id": f"{topic}:{i}", "title": title} for i, title in enumerate(items, start=1)]

                        if topic == "skin":
                            # Send exactly as requested for Skin: custom ids and labels, no header
                            payload_list = {
                                "messaging_product": "whatsapp",
                                "to": wa_id,
                                "type": "interactive",
                                "interactive": {
                                    "type": "list",
                                    "body": {"text": "Please select your Skin concern:"},
                                    "action": {
                                        "button": "Select Concern",
                                        "sections": [
                                            {
                                                "title": "Skin Concerns",
                                                "rows": [
                                                    {"id": "acne", "title": "Acne / Acne Scars"},
                                                    {"id": "pigmentation", "title": "Pigmentation & Uneven Skin Tone"},
                                                    {"id": "antiaging", "title": "Anti-Aging & Skin Rejuvenation"},
                                                    {"id": "laser", "title": "Laser Hair Removal"},
                                                    {"id": "other_skin", "title": "Other Skin Concerns"}
                                                ]
                                            }
                                        ]
                                    }
                                }
                            }
                            # Send to WA API
                            requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                            # Broadcast to ChatWindow so the UI shows the outgoing list
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "interactive",
                                    "message": "Please select your Skin concern:",
                                    "timestamp": datetime.now().isoformat(),
                                    "meta": {"kind": "list", "section": "Skin Concerns"}
                                })
                            except Exception:
                                pass
                            return {"status": "list_sent", "message_id": message_id}
                        elif topic == "hair":
                            rows = list_rows(["Hair Loss / Hair Fall", "Hair Transplant", "Dandruff & Scalp Care", "Other Hair Concerns"])
                            section_title = "Hair"
                        else:
                            # If BODY selected, trigger template body_treat_flow (no params) and STOP
                            if topic == "body":
                                try:
                                    from controllers.auto_welcome_controller import _send_template
                                    lang_code_body = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                                    resp_body = _send_template(
                                        wa_id=wa_id,
                                        template_name="body_treat_flow",
                                        access_token=token_entry2.token,
                                        phone_id=phone_id2,
                                        components=None,
                                        lang_code=lang_code_body
                                    )
                                    try:
                                        await manager.broadcast({
                                            "from": to_wa_id,
                                            "to": wa_id,
                                            "type": "template" if resp_body.status_code == 200 else "template_error",
                                            "message": "body_treat_flow sent" if resp_body.status_code == 200 else "body_treat_flow failed",
                                            **({"status_code": resp_body.status_code} if resp_body.status_code != 200 else {}),
                                            **({"error": (resp_body.text[:500] if isinstance(resp_body.text, str) else str(resp_body.text))} if resp_body.status_code != 200 else {}),
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    except Exception:
                                        pass
                                    return {"status": "body_template_sent", "message_id": message_id}
                                except Exception as e:
                                    try:
                                        await manager.broadcast({
                                            "from": to_wa_id,
                                            "to": wa_id,
                                            "type": "template_error",
                                            "message": f"body_treat_flow exception: {str(e)[:120]}",
                                            "timestamp": datetime.now().isoformat()
                                        })
                                    except Exception:
                                        pass
                            rows = list_rows(["Weight Management", "Body Contouring", "Weight Loss", "Other Body Concerns"])
                            section_title = "Body"

                      
                        # Send to WhatsApp API
                        requests.post(get_messages_url(phone_id2), headers=headers2, json=payload_list)
                        # Broadcast to ChatWindow so the UI shows the outgoing list
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "interactive",
                                "message": f"Please select your {section_title} concern:",
                                "timestamp": datetime.now().isoformat(),
                                "meta": {"kind": "list", "section": section_title}
                            })
                        except Exception:
                            pass
                        return {"status": "list_sent", "message_id": message_id}
            except Exception:
                pass

            # Follow-Up 1: User tapped Yes → trigger welcome and confirmation flow
            try:
                if i_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_id = (button_reply.get("id", "") or "").strip().lower()
                    if button_id == "followup_yes":
                        # Clear any pending follow-up timers but DON'T reset timer - mr_welcome will schedule a new one
                        try:
                            from services.followup_service import mark_customer_replied as _mark_replied
                            _mark_replied(db, customer_id=customer.id, reset_followup_timer=False)
                        except Exception:
                            pass
                        
                        # Set treatment flow context so subsequent messages use Treatment Flow number
                        try:
                            st_fu = appointment_state.get(wa_id) or {}
                            st_fu["flow_context"] = "treatment"
                            st_fu["from_treatment_flow"] = True
                            appointment_state[wa_id] = st_fu
                        except Exception:
                            pass
                        
                        # Resolve credentials for Treatment Flow number - force the SAME number that received followup_yes
                        from marketing.whatsapp_numbers import get_number_config, TREATMENT_FLOW_ALLOWED_PHONE_IDS, WHATSAPP_NUMBERS as _MAP
                        phone_id_fu = None
                        access_token_fu = None

                        # A) Prefer webhook metadata phone_number_id (the number that received the button reply)
                        try:
                            phone_id_meta_fu = (value or {}).get("metadata", {}).get("phone_number_id") if isinstance(value, dict) else None
                            if phone_id_meta_fu and str(phone_id_meta_fu) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                phone_id_fu = str(phone_id_meta_fu)
                        except Exception:
                            phone_id_fu = None

                        # B) If missing, infer from display_phone_number by last-10 digit match (allowed only)
                        if not phone_id_fu:
                            try:
                                import re as _re
                                disp_num_fu = ((value or {}).get("metadata", {}) or {}).get("display_phone_number") or to_wa_id or ""
                                disp_digits_fu = _re.sub(r"\\D", "", disp_num_fu or "")
                                disp_last10_fu = disp_digits_fu[-10:] if len(disp_digits_fu) >= 10 else disp_digits_fu
                                for _pid, _cfg in (_MAP or {}).items():
                                    if _pid in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                        name_digits_fu = _re.sub(r"\\D", "", (_cfg.get("name") or ""))
                                        name_last10_fu = name_digits_fu[-10:] if len(name_digits_fu) >= 10 else name_digits_fu
                                        if name_last10_fu and disp_last10_fu and name_last10_fu == disp_last10_fu:
                                            phone_id_fu = str(_pid)
                                            break
                            except Exception:
                                pass

                        # C) If still missing, fall back to stored phone id (if present)
                        if not phone_id_fu:
                            stored_phone_id_fu = st_fu.get("treatment_flow_phone_id")
                            if stored_phone_id_fu and str(stored_phone_id_fu) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                phone_id_fu = str(stored_phone_id_fu)

                        # D) Final fallback to first allowed
                        if not phone_id_fu:
                            phone_id_fu = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]

                        cfg_fu = get_number_config(str(phone_id_fu)) if phone_id_fu else None
                        access_token_fu = (cfg_fu.get("token") if (cfg_fu and cfg_fu.get("token")) else None)
                        if not access_token_fu:
                            from services.whatsapp_service import get_latest_token as _get_token
                            token_entry_fu = _get_token(db)
                            if token_entry_fu and token_entry_fu.token:
                                access_token_fu = token_entry_fu.token
                                # Store this phone_id in state for future use
                                try:
                                    st_fu["treatment_flow_phone_id"] = str(phone_id_fu)
                                    appointment_state[wa_id] = st_fu
                                except Exception:
                                    pass
                        
                        if access_token_fu:
                            lang_code_fu = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

                            # Send mr_welcome template from Treatment Flow number
                            from controllers.auto_welcome_controller import _send_template as _send_tpl
                            body_components_fu = [{
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": (sender_name or wa_id)}
                                ]
                            }]
                            resp_fu = _send_tpl(
                                wa_id=wa_id,
                                template_name="mr_welcome",
                                access_token=access_token_fu,
                                phone_id=str(phone_id_fu),
                                components=body_components_fu,
                                lang_code=lang_code_fu,
                            )
                            
                            # Mark mr_welcome as sent to prevent duplicates and store phone id
                            try:
                                st_fu_mark = appointment_state.get(wa_id) or {}
                                if resp_fu.status_code == 200:
                                    st_fu_mark["mr_welcome_sent"] = True
                                    st_fu_mark["treatment_flow_phone_id"] = str(phone_id_fu)
                                appointment_state[wa_id] = st_fu_mark
                            except Exception:
                                pass

                            # Schedule follow-up only for mr_welcome
                            try:
                                from services.followup_service import schedule_next_followup as _schedule, FOLLOW_UP_1_DELAY_MINUTES
                                _schedule(db, customer_id=customer.id, delay_minutes=FOLLOW_UP_1_DELAY_MINUTES, stage_label="mr_welcome_sent")
                            except Exception:
                                pass

                            # Send name/phone confirmation prompt from Treatment Flow number
                            try:
                                from services.customer_service import get_customer_record_by_wa_id
                                customer_rec = get_customer_record_by_wa_id(db, wa_id)
                                display_name = (customer_rec.name.strip() if customer_rec and isinstance(customer_rec.name, str) else None) or "there"
                                import re as _re
                                digits = _re.sub(r"\D", "", wa_id)
                                last10 = digits[-10:] if len(digits) >= 10 else None
                                display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
                            except Exception:
                                display_name = "there"
                                display_phone = wa_id

                            # Avoid duplicate confirmation if mr_welcome flow already sent it
                            try:
                                st_chk = appointment_state.get(wa_id) or {}
                                if not bool(st_chk.get("contact_confirm_sent")):
                                    await send_message_to_waid(wa_id, f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*", db, phone_id_hint=str(phone_id_fu))
                                    st_chk["contact_confirm_sent"] = True
                                    appointment_state[wa_id] = st_chk
                            except Exception:
                                await send_message_to_waid(wa_id, f"To help us serve you better, please confirm your contact details:\n*{display_name}*\n*{display_phone}*", db, phone_id_hint=str(phone_id_fu))

                            # Send Yes/No buttons for confirmation from Treatment Flow number
                            headers_btn = {"Authorization": f"Bearer {access_token_fu}", "Content-Type": "application/json"}
                            payload_btn = {
                                "messaging_product": "whatsapp",
                                "to": wa_id,
                                "type": "interactive",
                                "interactive": {
                                    "type": "button",
                                    "body": {"text": "Are your name and contact number correct? "},
                                    "action": {
                                        "buttons": [
                                            {"type": "reply", "reply": {"id": "confirm_yes", "title": "Yes"}},
                                            {"type": "reply", "reply": {"id": "confirm_no", "title": "No"}},
                                        ]
                                    },
                                },
                            }
                            requests.post(get_messages_url(str(phone_id_fu)), headers=headers_btn, json=payload_btn)
                        return {"status": "followup_yes_flow_started", "message_id": message_id}
            except Exception:
                pass

            # Appointment booking entry shortcuts
            try:
                if i_type == "button_reply":
                    button_reply = (interactive or {}).get("button_reply", {})
                    button_id = button_reply.get("id", "")
                    button_title = button_reply.get("title", "")
                    
                    # Book Appointment is now fully handled inside controllers.components.interactive_type.run_interactive_type
                    
                    if ((button_id or "").lower() == "request_callback" or 
                        (button_title or "").strip().lower() == "request a call back"):
                        await send_message_to_waid(wa_id, "📌 Thank you for your interest! One of our team members will contact you shortly to assist further.", db)
                        return {"status": "callback_ack", "message_id": message_id}
            except Exception:
                pass

            # Date picked from list
            try:
                if i_type == "list_reply" and (reply_id or "").lower().startswith("date_"):
                    date_iso = (reply_id or "")[5:]
                    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
                        appointment_state[wa_id] = {"date": date_iso}
                        await send_message_to_waid(wa_id, f"✅ Date selected: {date_iso}", db)
                        await send_time_buttons(wa_id, db)
                        return {"status": "date_selected", "message_id": message_id}
            except Exception:
                pass

            # Time picked from button reply (interactive path)
            try:
                if i_type == "button_reply":
                    button_reply = interactive.get("button_reply", {})
                    button_id = button_reply.get("id", "")
                    button_title = button_reply.get("title", "")
                    
                    if ((button_id or "").lower().startswith("time_") or 
                        (button_title or "").strip() in ["10:00 AM", "2:00 PM", "6:00 PM"]):
                        time_map = {
                            "time_10_00": "10:00 AM",
                            "time_14_00": "2:00 PM", 
                            "time_18_00": "6:00 PM",
                        }
                        time_label = (time_map.get((button_id or "").lower()) or 
                                    (button_title or "").strip())
                        date_iso = (appointment_state.get(wa_id) or {}).get("date")
                        if date_iso and time_label:
                            await _confirm_appointment(wa_id, db, date_iso, time_label)
                            return {"status": "appointment_captured", "message_id": message_id}
                    # Handle Yes/No confirmation for name/phone (accept common ids/titles)
                    norm_btn_id = (button_id or "").strip().lower()
                    norm_btn_title = (button_title or "").strip().lower()
                    yes_ids = {"confirm_yes", "yes", "y", "ok", "confirm"}
                    no_ids = {"confirm_no", "no", "n", "incorrect"}
                    if norm_btn_id in yes_ids or norm_btn_title in yes_ids or norm_btn_id in no_ids or norm_btn_title in no_ids:
                        # Retrieve stored date/time
                        date_iso = (appointment_state.get(wa_id) or {}).get("date")
                        time_label = (appointment_state.get(wa_id) or {}).get("time")
                        try:
                            from services.customer_service import get_customer_record_by_wa_id
                            customer = get_customer_record_by_wa_id(db, wa_id)
                            display_name = (customer.name.strip() if customer and isinstance(customer.name, str) else None) or "there"
                        except Exception:
                            display_name = "there"
                        # Derive phone from wa_id
                        try:
                            import re as _re
                            digits = _re.sub(r"\D", "", wa_id)
                            last10 = digits[-10:] if len(digits) >= 10 else None
                            display_phone = f"+91{last10}" if last10 and len(last10) == 10 else wa_id
                        except Exception:
                            display_phone = wa_id

                        # Check if this is from treatment flow
                        st = appointment_state.get(wa_id) or {}
                        from_treatment_flow = st.get("from_treatment_flow", False)
                        
                        if (norm_btn_id in yes_ids or norm_btn_title in yes_ids):
                            # Clear any pending interactive once user acts
                            try:
                                st.pop("pending_interactive", None)
                                appointment_state[wa_id] = st
                            except Exception:
                                pass
                            if from_treatment_flow:
                                # On Yes → proceed to city selection FIRST; mr_treatment will be sent after city selection
                                # Resolve phone_id from stored state or webhook metadata
                                phone_id_confirm = None
                                try:
                                    # First priority: stored treatment_flow_phone_id
                                    phone_id_confirm = st.get("treatment_flow_phone_id")
                                    if phone_id_confirm:
                                        phone_id_confirm = str(phone_id_confirm)
                                    # Second priority: webhook metadata phone_number_id
                                    if not phone_id_confirm:
                                        try:
                                            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                            phone_id_meta = (value or {}).get("metadata", {}).get("phone_number_id") if isinstance(value, dict) else None
                                            if phone_id_meta and str(phone_id_meta) in TREATMENT_FLOW_ALLOWED_PHONE_IDS:
                                                phone_id_confirm = str(phone_id_meta)
                                        except Exception:
                                            pass
                                    # Third priority: first allowed treatment flow number
                                    if not phone_id_confirm:
                                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                        phone_id_confirm = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                                except Exception:
                                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                    phone_id_confirm = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                                
                                try:
                                    from marketing.city_selection import send_city_selection  # type: ignore
                                    result = await send_city_selection(db, wa_id=wa_id, phone_id_hint=phone_id_confirm)
                                    return {"status": "proceed_to_city_selection", "message_id": message_id, "result": result}
                                except Exception as e:
                                    print(f"[treatment_flow] WARNING - Could not send city selection: {e}")
                                    return {"status": "failed", "message_id": message_id}
                            elif date_iso and time_label:
                                
                                # Regular appointment flow with date/time
                                thank_you = (
                                f"✅ Thank you! Your preferred appointment is on {date_iso} at {time_label} with {display_name} ({display_phone}). "
                                f"Your appointment is booked, and our team will call to confirm shortly."
                            )
                            # Persist appointment details to DB (create additional record for same wa_id)
                            try:
                                from services.referrer_service import referrer_service
                                existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                existing_treat = getattr(existing_ref, 'treatment_type', None) if existing_ref else ''
                                # Create a new appointment row (allow multiple per wa_id)
                                referrer_service.create_appointment_booking(
                                    db,
                                    wa_id,
                                    date_iso,
                                    time_label,
                                    existing_treat or ''
                                )
                            except Exception:
                                pass
                            await send_message_to_waid(wa_id, thank_you, db)
                            # Now clear state completely to allow new flow to start
                            try:
                                if wa_id in appointment_state:
                                    appointment_state.pop(wa_id, None)
                                # Also clear lead_appointment_state if present
                                if wa_id in lead_appointment_state:
                                    lead_appointment_state.pop(wa_id, None)
                                print(f"[ws_webhook] DEBUG - Cleared all flow state after appointment confirmation: wa_id={wa_id}")
                            except Exception:
                                pass
                            return {"status": "appointment_confirmed", "message_id": message_id}
                        elif (norm_btn_id in no_ids or norm_btn_title in no_ids):
                            # Ask for name first, then number (validated via OpenAI-backed validators)
                            try:
                                st = appointment_state.get(wa_id) or {}
                                # Try to recover date/time from DB if missing
                                if not st.get("date") or not st.get("time"):
                                    try:
                                        from services.referrer_service import referrer_service
                                        existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                        if existing_ref and getattr(existing_ref, "appointment_date", None) and getattr(existing_ref, "appointment_time", None):
                                            try:
                                                date_iso_rec = getattr(existing_ref.appointment_date, "date", None)()
                                                st["date"] = date_iso_rec.isoformat()
                                            except Exception:
                                                try:
                                                    st["date"] = existing_ref.appointment_date.strftime("%Y-%m-%d")
                                                except Exception:
                                                    pass
                                            st["time"] = existing_ref.appointment_time
                                    except Exception:
                                        pass
                                st["awaiting_name"] = True
                                st.pop("awaiting_phone", None)
                                st.pop("corrected_name", None)
                                st.pop("corrected_phone", None)
                                st.pop("pending_interactive", None)
                                appointment_state[wa_id] = st
                            except Exception:
                                pass
                            # Ensure this corrective message goes from the same number that started the flow
                            stored_phone_id = st.get("treatment_flow_phone_id")
                            phone_id_hint = stored_phone_id if stored_phone_id else None
                            if not phone_id_hint:
                                from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                            await send_message_to_waid(wa_id, "No problem. Let's update your details.\nPlease share your full name first.", db, phone_id_hint=str(phone_id_hint))
                            return {"status": "awaiting_name", "message_id": message_id}
                        else:
                            # Before sending user back, try to recover any existing appointment from DB
                            try:
                                from services.referrer_service import referrer_service
                                existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                if existing_ref and getattr(existing_ref, "appointment_date", None) and getattr(existing_ref, "appointment_time", None):
                                    st = appointment_state.get(wa_id) or {}
                                    try:
                                        date_iso_rec = getattr(existing_ref.appointment_date, "date", None)()
                                        st["date"] = date_iso_rec.isoformat()
                                    except Exception:
                                        try:
                                            st["date"] = existing_ref.appointment_date.strftime("%Y-%m-%d")
                                        except Exception:
                                            pass
                                    st["time"] = existing_ref.appointment_time
                                    appointment_state[wa_id] = st
                                    # If we recovered date/time and the user had pressed Yes earlier, confirm now
                                    if norm_btn_id in yes_ids or norm_btn_title in yes_ids:
                                        await _confirm_appointment(wa_id, db, st.get("date"), st.get("time"))
                                        return {"status": "appointment_captured", "message_id": message_id}
                                    # If it was not an explicit Yes, at least proceed to name capture without resetting flow
                                    stored_phone_id = st.get("treatment_flow_phone_id")
                                    phone_id_hint = stored_phone_id if stored_phone_id else None
                                    if not phone_id_hint:
                                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                        phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                                    await send_message_to_waid(wa_id, "No problem. Let's update your details.\nPlease share your full name first.", db, phone_id_hint=str(phone_id_hint))
                                    st["awaiting_name"] = True
                                    appointment_state[wa_id] = st
                                    return {"status": "awaiting_name", "message_id": message_id}
                            except Exception:
                                pass
                            # Fallback: ask to pick week/date
                            await send_message_to_waid(wa_id, "Please select a week and then a date.", db)
                            try:
                                from controllers.components.interactive_type import send_week_list  # type: ignore
                                await send_week_list(db, wa_id)
                            except Exception:
                                pass
                            return {"status": "need_date_first", "message_id": message_id}
            except Exception:
                pass

            # (Removed) Plain text YES/NO confirmations inside interactive branch to avoid duplication

            # Step 3 → 6: After a list selection, save+broadcast reply, then present next-step action buttons
            try:
                if (i_type in {"list_reply", "button_reply"}) and (reply_id or title):
                    # Store selected concern/treatment for later mapping to Zoho
                    # Prefer visible title; if only an ID is present, map to canonical title
                    selected_concern = title or reply_id or ""
                    # Normalize a few known IDs to display titles when Meta sends only IDs
                    # Normalize: prefer the exact title text when present
                    # If only an ID comes, translate to a canonical title once.
                    id_to_title_map = {
                        "acne": "Acne / Acne Scars",
                        "pigmentation": "Pigmentation & Uneven Skin Tone",
                        "antiaging": "Anti-Aging & Skin Rejuvenation",
                        "dandruff": "Dandruff & Scalp Care",
                        "other_skin": "Other Skin Concerns",
                        "hair_loss": "Hair Loss / Hair Fall",
                        "hair_transplant": "Hair Transplant",
                        "other_hair": "Other Hair Concerns",
                        "weight_mgmt": "Weight Management",
                        "body_contouring": "Body Contouring",
                        "other_body": "Other Body Concerns",
                    }
                    if (not title) and (reply_id or "").lower() in id_to_title_map:
                        selected_concern = id_to_title_map[(reply_id or "").lower()]
                    # Fallback for button payload structure
                    if not selected_concern:
                        try:
                            btn = (interactive or {}).get("button", {})
                            btn_text = btn.get("text") or btn.get("payload")
                            if btn_text:
                                selected_concern = btn_text
                        except Exception:
                            pass
                    # Canonicalize common variants (e.g., 'Skin: Acne' -> 'Acne / Acne Scars')
                    try:
                        def _canon(txt: str) -> str:
                            import re as _re
                            return _re.sub(r"[^a-z0-9]+", " ", (txt or "").lower()).strip()
                        raw = (selected_concern or "").strip()
                        # Remove optional category prefixes like "Skin: ", "Hair: ", "Body: "
                        for cat_prefix in ["skin:", "hair:", "body:"]:
                            if raw.lower().startswith(cat_prefix):
                                raw = raw[len(cat_prefix):].strip()
                        canon = _canon(raw)
                        synonyms_to_canonical = {
                            "acne": "Acne / Acne Scars",
                            "acne acne scars": "Acne / Acne Scars",
                            "pigmentation": "Pigmentation & Uneven Skin Tone",
                            "uneven skin tone": "Pigmentation & Uneven Skin Tone",
                            "anti aging": "Anti-Aging & Skin Rejuvenation",
                            "skin rejuvenation": "Anti-Aging & Skin Rejuvenation",
                            "dandruff": "Dandruff & Scalp Care",
                            "dandruff scalp care": "Dandruff & Scalp Care",
                            "laser hair removal": "Laser Hair Removal",
                            "hair loss hair fall": "Hair Loss / Hair Fall",
                            "hair transplant": "Hair Transplant",
                            "weight management": "Weight Management",
                            "body contouring": "Body Contouring",
                            "weight loss": "Weight Loss",
                            "other skin concerns": "Other Skin Concerns",
                            "other hair concerns": "Other Hair Concerns",
                            "other body concerns": "Other Body Concerns",
                        }
                        if canon in synonyms_to_canonical:
                            selected_concern = synonyms_to_canonical[canon]
                    except Exception:
                        pass

                    if selected_concern:
                        try:
                            if wa_id not in appointment_state:
                                appointment_state[wa_id] = {}
                            appointment_state[wa_id]["selected_concern"] = selected_concern
                            print(f"[treatment_flow] DEBUG - Stored selected concern: {selected_concern} (reply_id={reply_id}, title={title})")
                            # Also mirror into lead_appointment_state as fallback source
                            try:
                                if wa_id not in lead_appointment_state:
                                    lead_appointment_state[wa_id] = {}
                                lead_appointment_state[wa_id]["selected_concern"] = selected_concern
                                print(f"[lead_appointment_flow] DEBUG - Mirrored selected concern to lead_appointment_state: {selected_concern}")
                            except Exception as e:
                                print(f"[lead_appointment_flow] WARNING - Could not mirror selected concern: {e}")
                        except Exception as e:
                            print(f"[treatment_flow] WARNING - Could not store selected concern: {e}")
                    
                    # Do NOT rebroadcast here; unified early broadcast already did it.
                    # Trigger booking_appoint template right after treatment selection
                    try:
                        token_entry_book = get_latest_token(db)
                        if token_entry_book and token_entry_book.token:
                            phone_id_book = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")
                            lang_code_book = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
                            from controllers.auto_welcome_controller import _send_template
                            resp_book = _send_template(
                                wa_id=wa_id,
                                template_name="booking_appoint",
                                access_token=token_entry_book.token,
                                phone_id=phone_id_book,
                                components=None,
                                lang_code=lang_code_book
                            )
                            try:
                                await manager.broadcast({
                                    "from": to_wa_id,
                                    "to": wa_id,
                                    "type": "template" if resp_book.status_code == 200 else "template_error",
                                    "message": "booking_appoint sent" if resp_book.status_code == 200 else "booking_appoint failed",
                                    **({"status_code": resp_book.status_code} if resp_book.status_code != 200 else {}),
                                    **({"error": (resp_book.text[:500] if isinstance(resp_book.text, str) else str(resp_book.text))} if resp_book.status_code != 200 else {}),
                                    "timestamp": datetime.now().isoformat()
                                })
                            except Exception:
                                pass
                    except Exception:
                        pass

                    token_entry3 = get_latest_token(db)
                    if token_entry3 and token_entry3.token:
                        access_token3 = token_entry3.token
                        headers3 = {"Authorization": f"Bearer {access_token3}", "Content-Type": "application/json"}
                        phone_id3 = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

                        payload_buttons = {
                            "messaging_product": "whatsapp",
                            "to": wa_id,
                            "type": "interactive",
                            "interactive": {
                                "type": "button",
                                "body": {"text": "Please choose one of the following options:"},
                                "action": {
                                    "buttons": [
                                        {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 📅 Book an Appointment"}},
                                        {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde 📞 Request a Call Back"}}
                                    ]
                                }
                            }
                        }
                        # Broadcast first so UI shows event even if WA API fails
                        try:
                            await manager.broadcast({
                                "from": to_wa_id,
                                "to": wa_id,
                                "type": "interactive",
                                "message": "Please choose one of the following options:",
                                "timestamp": timestamp.isoformat(),
                                "meta": {"kind": "buttons", "options": ["📅 Book an Appointment", "📞 Request a Call Back"]}
                            })
                        except Exception:
                            pass
                        # Then attempt to send to WhatsApp API
                        requests.post(get_messages_url(phone_id3), headers=headers3, json=payload_buttons)
                        return {"status": "next_actions_sent", "message_id": message_id}
            except Exception:
                pass

            # Save and broadcast interactive reply only if we didn't already do it above
            if not interactive_broadcasted:
                reply_text = title or reply_id or "[Interactive Reply]"
                msg_interactive = MessageCreate(
                    message_id=message_id,
                    from_wa_id=from_wa_id,
                    to_wa_id=to_wa_id,
                    type="interactive",
                    body=reply_text,
                    timestamp=timestamp,
                    customer_id=customer.id,
                )
                # Save only; avoid second broadcast to prevent duplicates
                message_service.create_message(db, msg_interactive)
                db.commit()  # Explicitly commit the transaction

            # If user chose Buy Products → send only the WhatsApp catalog link (strict match)
            try:
                reply_text  # may be undefined if we already broadcast earlier
            except NameError:
                reply_text = title or reply_id or ""
            choice_text = (reply_text or "").strip().lower()
            if (reply_id and reply_id.lower() == "buy_products") or (choice_text == "buy products"):
                try:
                    await trigger_buy_products_from_welcome(db, wa_id=wa_id)
                except Exception:
                    pass
            return {"status": "success", "message_id": message_id}
        elif message_type == "document":
            document = message["document"]

            media_id = document.get("id")
            caption = document.get("caption", "")
            mime_type = document.get("mime_type", "")
            filename = document.get("filename", "")

            # Save document message in DB
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type="document",
                body=caption or "[Document]",
                timestamp=timestamp,
                customer_id=customer.id,
                media_id=media_id,
                caption=caption,
                filename=filename,
                mime_type=mime_type,
            )
            new_msg = message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction

            # Broadcast to WebSocket clients
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "document",
                "media_id": media_id,
                "caption": caption,
                "filename": filename,
                "mime_type": mime_type,
                "timestamp": timestamp.isoformat(),
            })

            return {"status": "success", "message_id": message_id}
        
        # Handle free-form text in treatment flow to capture name/phone even if user skips buttons
        # BUT: Only validate if message looks like name/phone input, not conversational text
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                if bool(st.get("from_treatment_flow")) and not bool(st.get("awaiting_name")) and not bool(st.get("awaiting_phone")):
                    # Check if message is conversational (contains common conversational phrases)
                    # If so, skip validation - user should use Yes/No buttons instead
                    conversational_indicators = [
                        "thanks", "thank", "hi", "hello", "hey", "please", "share", 
                        "your", "number", "want", "now", "need", "help", "ok", "okay"
                    ]
                    text_lower = body_text.lower()
                    is_conversational = any(indicator in text_lower for indicator in conversational_indicators) and len(body_text.split()) > 5
                    
                    # Also check if it's clearly a request/question rather than name/phone input
                    is_request = any(word in text_lower for word in ["share", "provide", "give", "send", "tell"])
                    
                    # Skip validation if message is clearly conversational or a request
                    if is_conversational or is_request:
                        # User is likely responding conversationally to Yes/No buttons
                        # Don't validate as name/phone, let the normal flow handle it
                        pass
                    else:
                        # Only validate if we are explicitly awaiting details (set after confirm_no)
                        # and the message looks like it might be name/phone input.
                        try:
                            st = appointment_state.get(wa_id) or {}
                        except Exception:
                            st = {}
                        awaiting_details = bool(st.get("awaiting_name") or st.get("awaiting_phone"))
                        if not awaiting_details:
                            # Not in details collection mode; ignore free-text here
                            pass
                        else:
                            # Must be relatively short and not contain request words
                            name_res = validate_human_name(body_text)
                            phone_res = validate_indian_phone(body_text)
                            name_ok = bool(name_res.get("valid")) and bool(name_res.get("name"))
                            phone_ok = bool(phone_res.get("valid")) and bool(phone_res.get("phone"))
                        if name_ok and phone_ok:
                            st["corrected_name"] = name_res.get("name").strip()
                            st["corrected_phone"] = phone_res.get("phone")
                            st["awaiting_name"] = False
                            st["awaiting_phone"] = False
                            appointment_state[wa_id] = st
                            # Update local customer record with corrected details
                            try:
                                from services.customer_service import get_customer_record_by_wa_id, update_customer
                                from schemas.customer_schema import CustomerUpdate
                                cust = get_customer_record_by_wa_id(db, wa_id)
                                if cust:
                                    # Normalize WA number to +91XXXXXXXXXX
                                    import re as _re
                                    wa_digits = _re.sub(r"\D", "", wa_id)
                                    wa_last10 = wa_digits[-10:] if len(wa_digits) >= 10 else wa_digits
                                    wa_norm = ("+91" + wa_last10) if len(wa_last10) == 10 else wa_id
                                update_customer(db, cust.id, CustomerUpdate(
                                    name=name_res.get("name").strip(),
                                    phone_2=phone_res.get("phone"),
                                ))
                            except Exception:
                                pass
                            # After capturing both, go to city selection
                            # Use marketing city_selection with phone_id_hint to send from same phone_id that triggered treatment flow
                            try:
                                stored_phone_id = st.get("treatment_flow_phone_id")
                                phone_id_hint = stored_phone_id if stored_phone_id else None
                                if not phone_id_hint:
                                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                    phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                                from marketing.city_selection import send_city_selection  # type: ignore
                                result = await send_city_selection(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
                                return {"status": "proceed_to_city_selection", "message_id": message_id, "result": result}
                            except Exception:
                                return {"status": "failed_after_details", "message_id": message_id}
                        elif awaiting_details and name_ok and not phone_ok:
                            # Only set awaiting_phone if the extracted name seems valid AND message is short (likely just a name)
                            # Don't trigger if message is long/conversational
                            if len(body_text.strip().split()) <= 5:
                                st["corrected_name"] = name_res.get("name").strip()
                                st["awaiting_name"] = False
                                st["awaiting_phone"] = True
                                appointment_state[wa_id] = st
                                import os as _os
                                _pid_hint2 = str(_os.getenv("TREATMENT_FLOW_PHONE_ID") or _os.getenv("WELCOME_PHONE_ID") or _os.getenv("WHATSAPP_PHONE_ID", "859830643878412"))
                                await send_message_to_waid(wa_id, f"Thanks {st['corrected_name']}! Now please share your number.", db, phone_id_hint=_pid_hint2)
                                return {"status": "name_captured_awaiting_phone", "message_id": message_id}
                        elif awaiting_details and phone_ok and not name_ok:
                            # Only set awaiting_name if the extracted phone seems valid AND message is short
                            if len(body_text.strip().split()) <= 5:
                                st["corrected_phone"] = phone_res.get("phone")
                                st["awaiting_name"] = True
                                st["awaiting_phone"] = False
                                appointment_state[wa_id] = st
                                await send_message_to_waid(wa_id, "Got your number. Please share your name (full name or first name).", db)
                                return {"status": "phone_captured_awaiting_name", "message_id": message_id}
        except Exception:
            pass
        
        # If free-text arrives while we are expecting an interactive reply, resend that interactive
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                awaiting_details = bool(st.get("awaiting_name") or st.get("awaiting_phone"))
                pend = st.get("pending_interactive") or {}
                pend_kind = pend.get("kind") if isinstance(pend, dict) else None
                # Throttle: only resend if at least 10s passed since prompt and not already resent
                from datetime import datetime as _dt
                pend_ts = None
                try:
                    pend_ts = _dt.fromisoformat(pend.get("ts")) if isinstance(pend.get("ts"), str) else None
                except Exception:
                    pend_ts = None
                resend_done = bool(pend.get("resend_done")) if isinstance(pend, dict) else True
                ok_to_resend = bool(pend_kind and not awaiting_details and not resend_done and pend_ts and (_dt.utcnow() - pend_ts).total_seconds() >= 10)
                if ok_to_resend:
                    # Schedule a delayed resend (12s) to avoid immediate duplication; abort if state changes
                    async def _delayed_resend_interactive():
                        try:
                            await asyncio.sleep(4)
                            st_now = appointment_state.get(wa_id) or {}
                            pnow = st_now.get("pending_interactive") or {}
                            if not isinstance(pnow, dict) or pnow.get("resend_done") or pnow.get("kind") != pend_kind:
                                return
                            if bool(st_now.get("awaiting_name") or st_now.get("awaiting_phone")):
                                return
                            # Resolve phone_id to resend from the same number
                            try:
                                stored_phone_id = st_now.get("treatment_flow_phone_id")
                                phone_id_hint = stored_phone_id if stored_phone_id else None
                                if not phone_id_hint:
                                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                    phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                            except Exception:
                                from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                            # Gentle clarification
                            await send_message_to_waid(wa_id, "We didn't quite get that. Please choose an option below.", db, phone_id_hint=str(phone_id_hint))
                            # Resend based on kind
                            try:
                                from services.whatsapp_service import get_latest_token as _get_tok
                                from config.constants import get_messages_url as _get_url
                                import requests as _req
                                from marketing.city_selection import send_city_selection as _send_city
                                from marketing.interactive import send_concern_buttons as _send_concern, send_next_actions as _send_next
                                tok = _get_tok(db)
                                if tok and tok.token:
                                    headers_r = {"Authorization": f"Bearer {tok.token}", "Content-Type": "application/json"}
                                    pid = str(phone_id_hint)
                                    if pend_kind == "confirm_contact":
                                        payload_btn = {
                                            "messaging_product": "whatsapp",
                                            "to": wa_id,
                                            "type": "interactive",
                                            "interactive": {
                                                "type": "button",
                                                "body": {"text": "Are your name and contact number correct? "},
                                                "action": {"buttons": [
                                                    {"type": "reply", "reply": {"id": "confirm_yes", "title": "Yes"}},
                                                    {"type": "reply", "reply": {"id": "confirm_no", "title": "No"}}
                                                ]}
                                            }
                                        }
                                        _req.post(_get_url(pid), headers=headers_r, json=payload_btn)
                                    elif pend_kind == "skin_concern_list":
                                        payload_list = {
                                            "messaging_product": "whatsapp",
                                            "to": wa_id,
                                            "type": "interactive",
                                            "interactive": {
                                                "type": "list",
                                                "body": {"text": "Please select your Skin concern:"},
                                                "action": {"button": "Select Concern", "sections": [{
                                                    "title": "Skin Concerns",
                                                    "rows": [
                                                        {"id": "acne", "title": "Acne / Acne Scars"},
                                                        {"id": "pigmentation", "title": "Pigmentation & Uneven Skin Tone"},
                                                        {"id": "antiaging", "title": "Anti-Aging & Skin Rejuvenation"},
                                                        {"id": "dandruff", "title": "Dandruff & Scalp Care"},
                                                        {"id": "other_skin", "title": "Other Skin Concerns"}
                                                    ]
                                                }]}
                                            }
                                        }
                                        _req.post(_get_url(pid), headers=headers_r, json=payload_list)
                                    elif pend_kind == "treatment_concerns":
                                        await _send_concern(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
                                    elif pend_kind == "city_selection":
                                        await _send_city(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
                                    elif pend_kind == "next_actions":
                                        payload_buttons = {
                                            "messaging_product": "whatsapp",
                                            "to": wa_id,
                                            "type": "interactive",
                                            "interactive": {
                                                "type": "button",
                                                "body": {"text": "Please choose one of the following options:"},
                                                "action": {"buttons": [
                                                    {"type": "reply", "reply": {"id": "book_appointment", "title": "\ud83d\udcc5 \ud83d\udcc5 Book an Appointment"}},
                                                    {"type": "reply", "reply": {"id": "request_callback", "title": "\ud83d\udcde \ud83d\udcde Request a Call Back"}}
                                                ]}
                                            }
                                        }
                                        _req.post(_get_url(pid), headers=headers_r, json=payload_buttons)
                            except Exception:
                                pass
                            # Mark one-time resend done
                            try:
                                st_update = appointment_state.get(wa_id) or {}
                                p = st_update.get("pending_interactive") or {}
                                if isinstance(p, dict):
                                    p["resend_done"] = True
                                    st_update["pending_interactive"] = p
                                    appointment_state[wa_id] = st_update
                            except Exception:
                                pass
                        except Exception:
                            pass
                    asyncio.create_task(_delayed_resend_interactive())
                    return {"status": "scheduled_resend_interactive", "message_id": message_id}
        except Exception:
            pass

        # If free-text arrives and last outbound was a template in treatment flow, resend that template once
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                flow_ctx = st.get("flow_context")
                if flow_ctx == "treatment":
                    pt = st.get("pending_template") or {}
                    tpl_name = pt.get("name") if isinstance(pt, dict) else None
                    from datetime import datetime as _dt
                    tpl_ts = None
                    try:
                        tpl_ts = _dt.fromisoformat(pt.get("ts")) if isinstance(pt.get("ts"), str) else None
                    except Exception:
                        tpl_ts = None
                    resend_done = bool(pt.get("resend_done")) if isinstance(pt, dict) else True
                    ok_to_resend_tpl = bool(tpl_name and not resend_done and tpl_ts and (_dt.utcnow() - tpl_ts).total_seconds() >= 10)
                    if ok_to_resend_tpl:
                        async def _delayed_resend_template():
                            try:
                                await asyncio.sleep(4)
                                st_now = appointment_state.get(wa_id) or {}
                                pt_now = st_now.get("pending_template") or {}
                                if not isinstance(pt_now, dict) or pt_now.get("resend_done") or pt_now.get("name") != tpl_name:
                                    return
                                try:
                                    stored_phone_id = st_now.get("treatment_flow_phone_id")
                                    phone_id_hint = stored_phone_id if stored_phone_id else None
                                    if not phone_id_hint:
                                        from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                        phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                                except Exception:
                                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                    phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                                # Resend template
                                try:
                                    from controllers.auto_welcome_controller import _send_template as _send_tpl
                                    from services.whatsapp_service import get_latest_token as _get_tok
                                    tok = _get_tok(db)
                                    if tok and tok.token:
                                        _send_tpl(
                                            wa_id=wa_id,
                                            template_name=str(tpl_name),
                                            access_token=tok.token,
                                            phone_id=str(phone_id_hint),
                                            components=None,
                                            lang_code=os.getenv("WELCOME_TEMPLATE_LANG", "en_US"),
                                        )
                                except Exception:
                                    pass
                                # Mark one-time resend done
                                try:
                                    st2 = appointment_state.get(wa_id) or {}
                                    p = st2.get("pending_template") or {}
                                    if isinstance(p, dict):
                                        p["resend_done"] = True
                                        st2["pending_template"] = p
                                        appointment_state[wa_id] = st2
                                except Exception:
                                    pass
                            except Exception:
                                pass
                        asyncio.create_task(_delayed_resend_template())
                        return {"status": "scheduled_resend_template", "message_id": message_id}
        except Exception:
            pass

        # Handle text while awaiting_name using OpenAI-backed validator
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                if bool(st.get("awaiting_name")):
                    # Check if message is conversational (not a name input)
                    conversational_indicators = [
                        "thanks", "thank", "hi", "hello", "hey", "please", "share", 
                        "your", "number", "want", "now", "need", "help", "ok", "okay"
                    ]
                    text_lower = body_text.lower()
                    is_conversational = any(indicator in text_lower for indicator in conversational_indicators) and len(body_text.split()) > 5
                    is_request = any(word in text_lower for word in ["share", "provide", "give", "send", "tell"])
                    
                    # Skip validation if message is clearly conversational or a request
                    if is_conversational or is_request:
                        # User is responding conversationally, not providing a name
                        # Don't validate - this shouldn't happen if awaiting_name is correctly set,
                        # but if it does, just skip validation to avoid incorrect error messages
                        pass
                    else:
                        result = validate_human_name(body_text)
                        if result.get("valid") and result.get("name"):
                            # Save corrected name and clear awaiting_name; ask for phone next
                            st["corrected_name"] = result.get("name").strip()
                            st["awaiting_name"] = False
                            st["awaiting_phone"] = True
                            appointment_state[wa_id] = st
                            # Use stored phone_id from treatment flow state
                            stored_phone_id = st.get("treatment_flow_phone_id")
                            phone_id_hint = stored_phone_id if stored_phone_id else None
                            if not phone_id_hint:
                                from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                            await send_message_to_waid(wa_id, f"Thanks {st['corrected_name']}! Now please share your number.", db, phone_id_hint=str(phone_id_hint))
                            return {"status": "name_captured_awaiting_phone", "message_id": message_id}
                        else:
                            # Use stored phone_id from treatment flow state
                            stored_phone_id = st.get("treatment_flow_phone_id")
                            phone_id_hint = stored_phone_id if stored_phone_id else None
                            if not phone_id_hint:
                                from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                            await send_message_to_waid(wa_id, "❌ That doesn't look like a valid name. Please send your full name or first name (letters only).", db, phone_id_hint=str(phone_id_hint))
                            return {"status": "invalid_name", "message_id": message_id}
        except Exception:
            pass

        # Handle text while awaiting_phone using validator
        try:
            if message_type == "text":
                st = appointment_state.get(wa_id) or {}
                if bool(st.get("awaiting_phone")):
                    phone_res = validate_indian_phone(body_text)
                    if phone_res.get("valid") and phone_res.get("phone"):
                        st["corrected_phone"] = phone_res.get("phone")
                        st["awaiting_phone"] = False
                        appointment_state[wa_id] = st
                        # Build final confirmation message with date/time and updated name/number
                        date_iso = (appointment_state.get(wa_id) or {}).get("date")
                        time_label = (appointment_state.get(wa_id) or {}).get("time")
                        name_final = (st.get("corrected_name") or "there").strip()
                        phone_final = st.get("corrected_phone")
                        from_treatment_flow = st.get("from_treatment_flow", False)
                        
                        if from_treatment_flow and name_final and phone_final:
                            # Update local customer record with corrected details
                            try:
                                from services.customer_service import get_customer_record_by_wa_id, update_customer
                                from schemas.customer_schema import CustomerUpdate
                                import re as _re
                                cust = get_customer_record_by_wa_id(db, wa_id)
                                if cust:
                                    wa_digits = _re.sub(r"\D", "", wa_id)
                                    wa_last10 = wa_digits[-10:] if len(wa_digits) >= 10 else wa_digits
                                    wa_norm = ("+91" + wa_last10) if len(wa_last10) == 10 else wa_id
                                    update_customer(db, cust.id, CustomerUpdate(name=name_final, phone_2=phone_final))
                            except Exception:
                                pass
                            # After capturing both, go to city selection
                            # Use marketing city_selection with phone_id_hint to send from same phone_id that triggered treatment flow
                            try:
                                stored_phone_id = st.get("treatment_flow_phone_id")
                                phone_id_hint = stored_phone_id if stored_phone_id else None
                                if not phone_id_hint:
                                    from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                                    phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                                from marketing.city_selection import send_city_selection  # type: ignore
                                result = await send_city_selection(db, wa_id=wa_id, phone_id_hint=str(phone_id_hint))
                                return {"status": "proceed_to_city_selection", "message_id": message_id, "result": result}
                            except Exception:
                                return {"status": "failed_after_details", "message_id": message_id}
                        elif date_iso and time_label and name_final and phone_final:
                            # Regular appointment flow with date/time
                            msg = (
                                f"✅ Thank you! Your preferred appointment is on {date_iso} at {time_label} "
                                f"with {name_final} ({phone_final}). Your appointment is booked, and our team will call to confirm shortly."
                            )
                            # Persist appointment details to DB (create additional record for same wa_id)
                            try:
                                from services.referrer_service import referrer_service
                                existing_ref = referrer_service.get_referrer_by_wa_id(db, wa_id)
                                existing_treat = getattr(existing_ref, 'treatment_type', None) if existing_ref else ''
                                # Create a new appointment row (allow multiple per wa_id)
                                referrer_service.create_appointment_booking(
                                    db,
                                    wa_id,
                                    date_iso,
                                    time_label,
                                    existing_treat or ''
                                )
                            except Exception:
                                pass
                            await send_message_to_waid(wa_id, msg, db)
                            # Clear state after confirmation completely to allow new flow to start
                            try:
                                if wa_id in appointment_state:
                                    appointment_state.pop(wa_id, None)
                                # Also clear lead_appointment_state if present
                                if wa_id in lead_appointment_state:
                                    lead_appointment_state.pop(wa_id, None)
                                print(f"[ws_webhook] DEBUG - Cleared all flow state after appointment confirmation (with details): wa_id={wa_id}")
                            except Exception:
                                pass
                            return {"status": "appointment_confirmed_after_details", "message_id": message_id}
                        else:
                            # Date/time should exist at this point (user tapped No on confirm).
                            # If somehow missing, prompt user to pick date again.
                            await send_message_to_waid(wa_id, "Please select a week and then a date.", db)
                            try:
                                from controllers.components.interactive_type import send_week_list  # type: ignore
                                await send_week_list(db, wa_id)
                            except Exception:
                                pass
                            return {"status": "need_date_first", "message_id": message_id}
                    else:
                        # Use stored phone_id from treatment flow state
                        stored_phone_id = st.get("treatment_flow_phone_id")
                        phone_id_hint = stored_phone_id if stored_phone_id else None
                        if not phone_id_hint:
                            from marketing.whatsapp_numbers import TREATMENT_FLOW_ALLOWED_PHONE_IDS
                            phone_id_hint = list(TREATMENT_FLOW_ALLOWED_PHONE_IDS)[0]
                        await send_message_to_waid(wa_id, "❌ That doesn't look like a valid Indian mobile number. Please send exactly 10 digits (or +91XXXXXXXXXX).", db, phone_id_hint=str(phone_id_hint))
                        return {"status": "invalid_phone", "message_id": message_id}
        except Exception:
            pass

        if message_type != "text":
            message_data = MessageCreate(
                message_id=message_id,
                from_wa_id=from_wa_id,
                to_wa_id=to_wa_id,
                type=message_type,
                body=body_text,
                timestamp=timestamp,
                customer_id=customer.id
            )
            message_service.create_message(db, message_data)
            db.commit()  # Explicitly commit the transaction
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": message_type,
                "message": message_data.body,
                "timestamp": message_data.timestamp.isoformat()
            })

        return {"status": "success", "message_id": message_id}

    except KeyError as e:
        print(f"Webhook error: Missing key in webhook payload - {e}")
        print("This might be a status update webhook that should be skipped")
        import traceback
        print(traceback.format_exc())
        return {"status": "ignored", "message": f"Missing key: {e}"}
    except Exception as e:
        print("Webhook error:", e)
        import traceback
        print(traceback.format_exc())
        return {"status": "failed", "error": str(e)}

@router.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WEBHOOK_VERIFIED")
        # implement the database insertion logic here and complete this function
        return PlainTextResponse(content=challenge)
    else:
          raise HTTPException(status_code=403)