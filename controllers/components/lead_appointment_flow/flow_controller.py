"""
Main Flow Controller for Lead-to-Appointment Booking Flow
Orchestrates the entire booking process from start to finish
"""

from datetime import datetime
import asyncio
from typing import Dict, Any, Optional
import re

from sqlalchemy.orm import Session
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def run_lead_appointment_flow(
    db: Session,
    *,
    wa_id: str,
    message_type: str,
    message_id: str,
    from_wa_id: str,
    to_wa_id: str,
    body_text: Optional[str] = None,
    timestamp: datetime,
    customer: Any,
    interactive: Optional[Dict[str, Any]] = None,
    i_type: Optional[str] = None,
    phone_number_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Main entry point for the Lead-to-Appointment Booking Flow.
    
    This function handles the complete flow from Meta ad click to appointment booking.
    It can be triggered by:
    1. Text messages (auto-welcome)
    2. Interactive responses (buttons/lists)
    3. Custom date inputs
    
    Returns a status dict.
    """
    
    try:
        # Broadcast incoming customer messages to WebSocket
        if message_type == "text" and body_text:
            try:
                await manager.broadcast({
                    "from": wa_id,
                    "to": from_wa_id,
                    "type": "text",
                    "message": body_text,
                    "timestamp": timestamp.isoformat(),
                    "meta": {"flow": "lead_appointment", "action": "customer_message"}
                })
                print(f"[lead_appointment_flow] DEBUG - Customer text message broadcasted to WebSocket")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - WebSocket broadcast failed: {e}")
        
        # Handle text messages - check for auto-welcome trigger
        if message_type == "text" and body_text:
            return await handle_text_message(
                db=db,
                wa_id=wa_id,
                body_text=body_text,
                customer=customer,
                timestamp=timestamp
            )
        
        # Handle interactive responses
        if message_type == "interactive" and interactive and i_type:
            # Broadcast interactive responses to WebSocket
            try:
                reply_text = ""
                if i_type == "button_reply":
                    reply_text = interactive.get("button_reply", {}).get("title", "")
                elif i_type == "list_reply":
                    reply_text = interactive.get("list_reply", {}).get("title", "")
                
                await manager.broadcast({
                    "from": wa_id,
                    "to": from_wa_id,
                    "type": "interactive",
                    "message": reply_text,
                    "timestamp": timestamp.isoformat(),
                    "meta": {"flow": "lead_appointment", "action": "customer_interaction", "i_type": i_type}
                })
                print(f"[lead_appointment_flow] DEBUG - Customer interactive response broadcasted to WebSocket")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - WebSocket broadcast failed: {e}")
            
            return await handle_interactive_response(
                db=db,
                wa_id=wa_id,
                interactive=interactive,
                i_type=i_type,
                customer=customer,
                timestamp=timestamp,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id
            )
        
        return {"status": "skipped"}
        
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Flow exception: {str(e)}")
        return {"status": "error", "error": str(e)}


async def handle_text_message(
    db: Session,
    *,
    wa_id: str,
    body_text: str,
    customer: Any,
    timestamp: datetime
) -> Dict[str, Any]:
    """Handle text messages in the lead appointment flow.
    
    This includes:
    1. Auto-welcome triggers
    2. Custom date inputs
    3. General text responses
    """
    
    # Check for auto-welcome triggers
    # Normalize text: lowercase, normalize whitespace, remove trailing periods
    # Also handle special characters and Unicode variations
    try:
        # Normalize Unicode characters (e.g., smart quotes, apostrophes)
        import unicodedata
        body_text_normalized = unicodedata.normalize('NFKC', body_text)
        # Replace various apostrophe/quote characters with standard apostrophe
        body_text_normalized = body_text_normalized.replace("'", "'").replace("'", "'").replace("'", "'")
        body_text_normalized = body_text_normalized.replace(""", '"').replace(""", '"')
    except Exception:
        # Fallback if unicodedata not available
        body_text_normalized = body_text.replace("'", "'").replace("'", "'")
    
    normalized_text = ' '.join(body_text_normalized.lower().strip().rstrip('.').split())
    
    # Debug logging for server troubleshooting
    print(f"[lead_appointment_flow] DEBUG - handle_text_message called: wa_id={wa_id}")
    print(f"[lead_appointment_flow] DEBUG - Original body_text (first 150 chars): '{body_text[:150]}'")
    print(f"[lead_appointment_flow] DEBUG - Normalized text (first 150 chars): '{normalized_text[:150]}'")
    
    # Specific starting point messages from WhatsApp links
    # These are the exact messages that come from WhatsApp links when customers click them
    link_starting_points = [
        "hi! i saw your ad for oliva's hair regrowth treatments and want to know more",
        "hi! i saw your ad for oliva's precision+ laser hair reduction and want to know more",
        "hi! i saw your ad for oliva's skin brightening treatments and want to know more",
        "hi! i saw your ad for oliva's acne & scar treatments and want to know more",
        "hi! i saw your ad for oliva's skin boosters and want to know more",
    ]
    
    # Also check for messages that contain the key pattern "i saw your ad for oliva" and "want to know more"
    # Use "oliva" without apostrophe to handle all Unicode variants
    # This handles variations in punctuation, extra whitespace, etc.
    # NOTE: Location inquiry messages ("want to know more about services in...") should NOT match here
    # They should be handled by the TREATMENT flow instead
    has_link_pattern = (
        "i saw your ad for oliva" in normalized_text 
        and "want to know more" in normalized_text
    )
    
    # Generic keyword triggers (fallback for older behavior)
    welcome_triggers = [
        "book", "appointment", "inquire", "inquiry", "consultation", "visit", "schedule"
    ]
    
    # Check if message matches any starting point message (exact match after normalization)
    # Normalize apostrophes in the starting points list to match
    normalized_starting_points = [point.replace("'", "'").replace("'", "'") for point in link_starting_points]
    is_starting_point = normalized_text in normalized_starting_points
    
    # Also check for generic triggers
    has_generic_trigger = any(trigger in normalized_text for trigger in welcome_triggers)
    
    # NOTE: Location inquiry messages like "want to know more about services in..." should go to TREATMENT flow
    # They are handled by run_treament_flow which has a prefill_regex pattern for them
    if is_starting_point or has_link_pattern or has_generic_trigger:
        # Initialize lead appointment flow state immediately when starting point message is detected
        try:
            from controllers.web_socket import lead_appointment_state
            if wa_id not in lead_appointment_state:
                lead_appointment_state[wa_id] = {}
            lead_appointment_state[wa_id]["flow_context"] = "lead_appointment"
            # Set default Zoho fields for lead appointment flow
            lead_appointment_state[wa_id]["lead_source"] = "Facebook"
            lead_appointment_state[wa_id]["language"] = "English"
            
            # Map starting point message to concern for Zoho
            concern_mapping = {
                "hi! i saw your ad for oliva's hair regrowth treatments and want to know more": "Hair Loss / PRP",
                "hi! i saw your ad for oliva's precision+ laser hair reduction and want to know more": "LHR",
                "hi! i saw your ad for oliva's skin brightening treatments and want to know more": "LT",
                "hi! i saw your ad for oliva's acne & scar treatments and want to know more": "Scars",
                "hi! i saw your ad for oliva's skin boosters and want to know more": "Anti ageing",
            }
            
            # Extract concern from message
            matched_concern = None
            if is_starting_point:
                matched_concern = concern_mapping.get(normalized_text)
            elif has_link_pattern:
                # Try to extract concern from message pattern
                if "hair regrowth" in normalized_text:
                    matched_concern = "Hair Loss / PRP"
                elif "precision+" in normalized_text or "laser hair reduction" in normalized_text:
                    matched_concern = "LHR"
                elif "skin brightening" in normalized_text:
                    matched_concern = "LT"
                elif "acne" in normalized_text or "scar" in normalized_text:
                    matched_concern = "Scars"
                elif "skin boosters" in normalized_text:
                    matched_concern = "Anti ageing"
            
            if matched_concern:
                lead_appointment_state[wa_id]["selected_concern"] = matched_concern
                lead_appointment_state[wa_id]["zoho_mapped_concern"] = matched_concern
                print(f"[lead_appointment_flow] DEBUG - Mapped concern from starting point: {matched_concern}")
            
            print(f"[lead_appointment_flow] DEBUG - Initialized lead appointment flow context for {wa_id}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not initialize lead appointment flow context: {e}")
        
        from .auto_welcome import send_auto_welcome_message
        result = await send_auto_welcome_message(db, wa_id=wa_id)
        # Schedule Follow-Up 1 after 5 minutes if no reply to auto-welcome
        try:
            from .follow_up1 import schedule_follow_up1_after_welcome
            sent_at = datetime.utcnow()
            asyncio.create_task(schedule_follow_up1_after_welcome(wa_id, sent_at))
        except Exception as _e:
            # Non-fatal if scheduling fails; continue flow
            pass
        return {"status": "auto_welcome_sent", "result": result}
    
    return {"status": "skipped"}


async def handle_interactive_response(
    db: Session,
    *,
    wa_id: str,
    interactive: Dict[str, Any],
    i_type: str,
    customer: Any,
    timestamp: datetime,
    phone_number_id: Optional[str] = None,
    to_wa_id: Optional[str] = None
) -> Dict[str, Any]:
    """Handle interactive responses (buttons/lists) in the lead appointment flow."""
    
    try:
        # Extract reply information
        if i_type == "button_reply":
            reply_data = interactive.get("button_reply", {})
            reply_id = reply_data.get("id", "")
            reply_title = reply_data.get("title", "")
        elif i_type == "list_reply":
            reply_data = interactive.get("list_reply", {})
            reply_id = reply_data.get("id", "")
            reply_title = reply_data.get("title", "")
        else:
            return {"status": "skipped"}
        
        print(f"[lead_appointment_flow] DEBUG - Handling interactive response: {reply_id} - {reply_title}")
        print(f"[lead_appointment_flow] DEBUG - Reply ID analysis: starts_with_time={reply_id.startswith('time_')}, count_underscores={reply_id.count('_')}, split_length={len(reply_id.split('_'))}")
        
        # Mark customer as replied for ANY interactive response in lead appointment flow
        # This ensures follow-up timer resets from user's last interaction
        try:
            from services.followup_service import mark_customer_replied as _mark_replied
            _mark_replied(db, customer_id=customer.id, reset_followup_timer=True)
            print(f"[lead_appointment_flow] DEBUG - Customer {wa_id} interactive reply ({i_type}: {reply_id}) - reset follow-up timer")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not mark customer replied for interactive: {e}")
        
        # Route to appropriate handler based on reply_id
        if reply_id == "followup_yes":
            # User tapped Yes in Follow-Up 1 → re-trigger auto-welcome template and re-schedule FU1
            from .auto_welcome import send_auto_welcome_message
            result = await send_auto_welcome_message(db, wa_id=wa_id)
            try:
                from .follow_up1 import schedule_follow_up1_after_welcome
                sent_at = datetime.utcnow()
                asyncio.create_task(schedule_follow_up1_after_welcome(wa_id, sent_at))
            except Exception:
                pass
            return {"status": "followup_yes_retriggered", "result": result}
        
        if reply_id.startswith("yes_book_appointment") or reply_id.startswith("not_now") or reply_id.startswith("book_appointment"):
            # Auto-welcome response (including "Book Appointment" from Not Now flow)
            from .auto_welcome import handle_welcome_response
            return await handle_welcome_response(
                db=db,
                wa_id=wa_id,
                reply_id=reply_id,
                customer=customer
            )
        
        elif reply_id.startswith("city_"):
            # City selection response - only handle if this is lead appointment flow number
            from .city_selection import handle_city_selection
            return await handle_city_selection(
                db=db,
                wa_id=wa_id,
                reply_id=reply_id,
                customer=customer,
                phone_number_id=phone_number_id,
                to_wa_id=to_wa_id
            )
        
        elif reply_id.startswith("clinic_"):
            # Clinic location response
            from .clinic_location import handle_clinic_location
            return await handle_clinic_location(
                db=db,
                wa_id=wa_id,
                reply_id=reply_id,
                customer=customer
            )
        
        
        elif reply_id.startswith("yes_callback"):
            # User wants callback - trigger auto dial
            return await handle_yes_callback(db, wa_id=wa_id, customer=customer)
        
        elif reply_id.startswith("no_callback_not_now"):
            # User doesn't want callback right now - send follow-up message
            return await handle_no_callback_not_now(db, wa_id=wa_id, customer=customer)
        
        # Handle week/date/time selections ONLY if user is in lead appointment flow
        # Check if user is in lead appointment flow before handling time selections
        try:
            from controllers.web_socket import lead_appointment_state
            is_in_lead_flow = wa_id in lead_appointment_state and lead_appointment_state[wa_id]
            print(f"[lead_appointment_flow] DEBUG - User {wa_id} in lead appointment flow: {is_in_lead_flow}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not check lead appointment state: {e}")
            is_in_lead_flow = False
        
        # Only handle time selections if user is explicitly in lead appointment flow
        if is_in_lead_flow:
            if reply_id.startswith("week_"):
                # Week selection - go directly to time slot categories (skip date selection)
                from controllers.components.interactive_type import _send_lead_time_slot_categories
                
                # Store selected week in session for lead creation
                try:
                    from controllers.web_socket import lead_appointment_state
                    if wa_id not in lead_appointment_state:
                        lead_appointment_state[wa_id] = {}
                    
                    # Extract week range from reply_id (format: week_YYYY-MM-DD_YYYY-MM-DD)
                    parts = reply_id.split("_")
                    if len(parts) >= 3:
                        start_iso = f"{parts[1]}-{parts[2]}-{parts[3]}"
                        end_iso = f"{parts[4]}-{parts[5]}-{parts[6]}"
                        lead_appointment_state[wa_id]["selected_week"] = f"{start_iso} to {end_iso}"
                        print(f"[lead_appointment_flow] DEBUG - Stored selected week: {start_iso} to {end_iso}")
                    else:
                        lead_appointment_state[wa_id]["selected_week"] = "Selected week"
                        print(f"[lead_appointment_flow] DEBUG - Stored generic week selection")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not store week selection: {e}")
                
                # Go directly to time slot categories
                result = await _send_lead_time_slot_categories(db=db, wa_id=wa_id)
                return {"status": "time_slots_sent", "result": result}
            
            # elif reply_id.startswith("date_"):
            #     # Date selection - COMMENTED OUT - now going directly from week to time slots
            #     # First, sync the selected date to lead_appointment_state
            #     try:
            #         date_iso = reply_id[5:]  # Extract date from "date_YYYY-MM-DD"
            #         from controllers.web_socket import lead_appointment_state
            #         if wa_id not in lead_appointment_state:
            #             lead_appointment_state[wa_id] = {}
            #         lead_appointment_state[wa_id]["selected_date"] = date_iso
            #         print(f"[lead_appointment_flow] DEBUG - Synced selected date to lead_appointment_state: {date_iso}")
            #     except Exception as e:
            #         print(f"[lead_appointment_flow] WARNING - Could not sync date to lead_appointment_state: {e}")
            #     
            #     # Use LEAD APPOINTMENT specific time slot categories function
            #     from controllers.components.interactive_type import _send_lead_time_slot_categories
            #     result = await _send_lead_time_slot_categories(db=db, wa_id=wa_id)
            #     return {"status": "time_slots_sent", "result": result}
            
            elif reply_id.startswith("slot_"):
                # Time slot category selection - send thank you directly (skip specific time selection)
                print(f"[lead_appointment_flow] DEBUG - Handling slot selection: {reply_id}")
                
                # Store the selected slot for lead creation
                try:
                    from controllers.web_socket import lead_appointment_state
                    if wa_id not in lead_appointment_state:
                        lead_appointment_state[wa_id] = {}
                    
                    # Map slot_id to human-readable name
                    slot_names = {
                        "slot_morning": "Morning (9-11 AM)",
                        "slot_afternoon": "Afternoon (12-4 PM)",
                        "slot_evening": "Evening (5-7 PM)"
                    }
                    slot_name = slot_names.get(reply_id, reply_id)
                    lead_appointment_state[wa_id]["selected_time"] = slot_name
                    print(f"[lead_appointment_flow] DEBUG - Stored selected time slot: {slot_name}")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not store slot selection: {e}")
                
                # Send callback confirmation message
                result = await send_callback_confirmation_interactive(db, wa_id=wa_id, customer=customer)
                return {"status": "callback_confirmation_sent", "result": result}
            
            elif reply_id.startswith("time_") and (
                # Handle specific time formats: time_1630, time_10_00, time_14_00, etc.
                (len(reply_id) >= 8 and reply_id[5:].isdigit()) or  # time_1630 format
                (reply_id.count("_") >= 2 and reply_id.split("_")[2].isdigit())  # time_10_00 format
            ):
                # Specific time selection - send callback confirmation
                print(f"[lead_appointment_flow] DEBUG - Handling time selection: {reply_id}")
                
                # Store the selected time
                try:
                    from controllers.web_socket import lead_appointment_state
                    if wa_id not in lead_appointment_state:
                        lead_appointment_state[wa_id] = {}
                    
                    # Extract time from reply_id (time_1630 or time_10_00 format)
                    time_value = reply_id.replace("time_", "").replace("_", ":")
                    lead_appointment_state[wa_id]["selected_time"] = time_value
                    print(f"[lead_appointment_flow] DEBUG - Stored selected time: {time_value}")
                except Exception as e:
                    print(f"[lead_appointment_flow] WARNING - Could not store time selection: {e}")
                
                # Send callback confirmation message
                result = await send_callback_confirmation_interactive(db, wa_id=wa_id, customer=customer)
                return {"status": "callback_confirmation_sent", "result": result}
        else:
            # User is NOT in lead appointment flow - skip time selections to let treatment flow handle them
            if (reply_id.startswith("week_") or 
                reply_id.startswith("date_") or 
                reply_id.startswith("slot_") or 
                reply_id.startswith("time_")):
                print(f"[lead_appointment_flow] DEBUG - User {wa_id} not in lead appointment flow, skipping {reply_id} - let treatment flow handle it")
                return {"status": "skipped"}
        
        return {"status": "skipped"}
        
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Interactive response handling failed: {str(e)}")
        return {"status": "error", "error": str(e)}


async def handle_flow_dropoff(
    db: Session,
    *,
    wa_id: str,
    customer: Any,
    dropoff_point: str
) -> Dict[str, Any]:
    """Handle users who drop off during the flow.
    
    Creates a lead with NO_CALLBACK status for tracking purposes.
    """
    
    try:
        from .zoho_lead_service import handle_termination_event
        result = await handle_termination_event(
            db=db,
            wa_id=wa_id,
            customer=customer,
            termination_reason=dropoff_point,
            appointment_details={}
        )
        
        print(f"[lead_appointment_flow] DEBUG - Created dropoff lead for {wa_id} at {dropoff_point}")
        return {"status": "dropoff_lead_created", "result": result}
        
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Dropoff handling failed: {str(e)}")
        return {"status": "error", "error": str(e)}


def is_lead_appointment_flow_active(wa_id: str) -> bool:
    """Check if a user is currently in the lead appointment flow.
    
    Returns True if the user has any session data for this flow.
    """
    
    try:
        from controllers.web_socket import lead_appointment_state
        return wa_id in lead_appointment_state and bool(lead_appointment_state[wa_id])
    except Exception:
        return False


def get_flow_progress(wa_id: str) -> Dict[str, Any]:
    """Get the current progress of a user in the lead appointment flow.
    
    Returns a dictionary with flow progress information.
    """
    
    try:
        from controllers.web_socket import lead_appointment_state
        session_data = lead_appointment_state.get(wa_id, {})
        
        progress = {
            "is_active": bool(session_data),
            "selected_city": session_data.get("selected_city"),
            "selected_clinic": session_data.get("selected_clinic"),
            "custom_date": session_data.get("custom_date"),
            "waiting_for_custom_date": session_data.get("waiting_for_custom_date", False),
            "clinic_id": session_data.get("clinic_id")
        }
        
        return progress
        
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Could not get flow progress: {str(e)}")
        return {"is_active": False, "error": str(e)}


async def send_callback_confirmation_interactive(
    db: Session,
    *,
    wa_id: str,
    customer: Any
) -> Dict[str, Any]:
    """Send interactive message asking if user wants a callback.
    
    Returns a status dict.
    """
    
    try:
        from services.whatsapp_service import get_latest_token
        from config.constants import get_messages_url
        import os
        import requests
        
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to send message right now.", db)
            return {"success": False, "error": "no_token"}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        # Send interactive message with buttons
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": 
"Thank you for sharing your preferred location & time. *Your appointment is not yet confirmed*\nWould you like our agent to call you to confirm your appointment?"
                },
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "yes_callback", "title": "Yes"}},
                        {"type": "reply", "reply": {"id": "no_callback_not_now", "title": "Not right now"}}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        
        if resp.status_code == 200:
            message_id = f"outbound_{datetime.now().timestamp()}"
            try:
                # Get message ID from response
                response_data = resp.json()
                message_id = response_data.get("messages", [{}])[0].get("id", message_id)
                
                # Save outbound message to database
                from services.message_service import create_message
                from schemas.message_schema import MessageCreate
                
                outbound_message = MessageCreate(
                    message_id=message_id,
                    from_wa_id=os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    to_wa_id=wa_id,
                    type="interactive",
                    body="Thank you for sharing your preferred location & time. *Your appointment is not yet confirmed*\nWould you like our agent to call you to confirm your appointment?",
                    timestamp=datetime.now(),
                    customer_id=customer.id,
                )
                create_message(db, outbound_message)
                print(f"[lead_appointment_flow] DEBUG - Callback confirmation message saved to database: {message_id}")
                
                # Broadcast to WebSocket
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Thank you for sharing your preferred location & time. *Your appointment is not yet confirmed*\nWould you like our agent to call you to confirm your appointment?",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "buttons",
                        "options": ["Yes", "Not right now"]
                    }
                })
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Database save or WebSocket broadcast failed: {e}")
            # Arm Follow-Up 1 after this outbound prompt in case user stops here
            try:
                import asyncio
                from .follow_up1 import schedule_follow_up1_after_welcome
                asyncio.create_task(schedule_follow_up1_after_welcome(wa_id, datetime.utcnow()))
            except Exception:
                pass
            
            return {"success": True, "message_id": message_id}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send message. Please try again.", db)
            return {"success": False, "error": resp.text}
            
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending message: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def handle_yes_callback(
    db: Session,
    *,
    wa_id: str,
    customer: Any
) -> Dict[str, Any]:
    """Handle yes callback - trigger auto dial.
    
    Returns a status dict.
    """
    
    try:
        print(f"[lead_appointment_flow] DEBUG - User requested callback (Yes)")
        
        # Get appointment details from session state
        appointment_details = {}
        try:
            from controllers.web_socket import lead_appointment_state
            appointment_details = lead_appointment_state.get(wa_id, {})
            print(f"[lead_appointment_flow] DEBUG - Appointment details: {appointment_details}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not get appointment details: {e}")
        
        # Trigger Q5 auto dial event
        from .zoho_lead_service import trigger_q5_auto_dial_event
        result = await trigger_q5_auto_dial_event(
            db=db,
            wa_id=wa_id,
            customer=customer,
            appointment_details=appointment_details
        )
        
        if result["success"]:
            # Send confirmation message
            await send_message_to_waid(
                wa_id, 
                "✅ Perfect! We've noted your appointment details and one of our agents will call you shortly to confirm your appointment. Thank you! 😊", 
                db
            )
            
            # Clear session data
            try:
                from controllers.web_socket import lead_appointment_state
                if wa_id in lead_appointment_state:
                    del lead_appointment_state[wa_id]
                print(f"[lead_appointment_flow] DEBUG - Cleared appointment session data")
            except Exception as e:
                print(f"[lead_appointment_flow] WARNING - Could not clear session data: {e}")
        
        return {"status": "callback_triggered", "result": result}
        
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Failed to trigger callback: {e}")
        await send_message_to_waid(
            wa_id, 
            "✅ Perfect! We've noted your appointment details and one of our agents will call you shortly. Thank you! 😊", 
            db
        )
        return {"status": "error", "error": str(e)}


async def handle_no_callback_not_now(
    db: Session,
    *,
    wa_id: str,
    customer: Any
) -> Dict[str, Any]:
    """Handle no callback not now - send text message and create lead.
    
    Returns a status dict.
    """
    
    try:
        import os
        
        # Get appointment details from session state
        appointment_details = {}
        try:
            from controllers.web_socket import lead_appointment_state
            appointment_details = lead_appointment_state.get(wa_id, {})
            print(f"[lead_appointment_flow] DEBUG - Appointment details: {appointment_details}")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not get appointment details: {e}")
        
        # Send plain text message
        message = "No problem! You can reach out anytime to schedule your appointment.\n\n✅ 8 lakh+ clients have trusted Oliva & experienced visible transformation\n\nWe'll be right here whenever you're ready to start your journey. 🌿"
        await send_message_to_waid(wa_id, message, db)
        
        # Broadcast to WebSocket
        try:
            await manager.broadcast({
                "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                "to": wa_id,
                "type": "text",
                "message": message,
                "timestamp": datetime.now().isoformat(),
                "meta": {"flow": "lead_appointment", "action": "not_right_now_sent"}
            })
            print(f"[lead_appointment_flow] DEBUG - Not right now message broadcasted to WebSocket")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - WebSocket broadcast failed: {e}")
        
        # Create lead in Zoho with NO_CALLBACK status
        try:
            from .zoho_lead_service import handle_termination_event
            termination_result = await handle_termination_event(
                db=db,
                wa_id=wa_id,
                customer=customer,
                termination_reason="not_right_now",
                appointment_details=appointment_details
            )
            print(f"[lead_appointment_flow] DEBUG - Lead created with not right now status")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not create lead: {e}")
        
        # Clear session data
        try:
            from controllers.web_socket import lead_appointment_state
            if wa_id in lead_appointment_state:
                del lead_appointment_state[wa_id]
            print(f"[lead_appointment_flow] DEBUG - Cleared appointment session data")
        except Exception as e:
            print(f"[lead_appointment_flow] WARNING - Could not clear session data: {e}")
        
        return {"status": "not_right_now_sent"}
        
    except Exception as e:
        print(f"[lead_appointment_flow] ERROR - Failed to send not right now message: {e}")
        await send_message_to_waid(
            wa_id, 
            "Thank you for your interest! We'll be here when you're ready. 😊", 
            db
        )
        return {"status": "error", "error": str(e)}
