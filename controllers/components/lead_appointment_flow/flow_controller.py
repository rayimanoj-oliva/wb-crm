"""
Main Flow Controller for Lead-to-Appointment Booking Flow
Orchestrates the entire booking process from start to finish
"""

from datetime import datetime
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
                timestamp=timestamp
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
    
    # Check for auto-welcome triggers (excluding hi/hello to avoid conflicts with treatment flow)
    normalized_text = body_text.lower().strip()
    welcome_triggers = [
        "book", "appointment", "inquire", "inquiry", "consultation", "visit", "schedule"
    ]
    
    if any(trigger in normalized_text for trigger in welcome_triggers):
        from .auto_welcome import send_auto_welcome_message
        result = await send_auto_welcome_message(db, wa_id=wa_id)
        return {"status": "auto_welcome_sent", "result": result}
    
    return {"status": "skipped"}


async def handle_interactive_response(
    db: Session,
    *,
    wa_id: str,
    interactive: Dict[str, Any],
    i_type: str,
    customer: Any,
    timestamp: datetime
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
        
        # Route to appropriate handler based on reply_id
        if reply_id.startswith("yes_book_appointment") or reply_id.startswith("not_now"):
            # Auto-welcome response
            from .auto_welcome import handle_welcome_response
            return await handle_welcome_response(
                db=db,
                wa_id=wa_id,
                reply_id=reply_id,
                customer=customer
            )
        
        elif reply_id.startswith("city_"):
            # City selection response
            from .city_selection import handle_city_selection
            return await handle_city_selection(
                db=db,
                wa_id=wa_id,
                reply_id=reply_id,
                customer=customer
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
        
        
        elif reply_id.startswith("yes_callback") or reply_id.startswith("no_callback"):
            # Callback confirmation response
            from .callback_confirmation import handle_callback_confirmation
            return await handle_callback_confirmation(
                db=db,
                wa_id=wa_id,
                reply_id=reply_id,
                customer=customer
            )
        
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
                
                # Send thank you message and create lead
                try:
                    # Get appointment details from session for logging
                    appointment_details = {}
                    try:
                        from controllers.web_socket import lead_appointment_state
                        appointment_details = lead_appointment_state.get(wa_id, {})
                        print(f"[lead_appointment_flow] DEBUG - Appointment details: {appointment_details}")
                    except Exception as e:
                        print(f"[lead_appointment_flow] WARNING - Could not get appointment details: {e}")
                    
                    # Send thank you message
                    thank_you_message = "✅ Thank you! We've noted your appointment details and our team will get back to you shortly to confirm your appointment. 😊"
                    await send_message_to_waid(wa_id, thank_you_message, db)
                    
                    # Broadcast to WebSocket
                    try:
                        await manager.broadcast({
                            "from": "system",
                            "to": wa_id,
                            "type": "text",
                            "message": thank_you_message,
                            "timestamp": datetime.now().isoformat(),
                            "meta": {"flow": "lead_appointment", "action": "thank_you_sent"}
                        })
                        print(f"[lead_appointment_flow] DEBUG - Thank you message broadcasted to WebSocket")
                    except Exception as e:
                        print(f"[lead_appointment_flow] WARNING - WebSocket broadcast failed: {e}")
                    
                    # Create lead in Zoho (if integration is available)
                    try:
                        from .zoho_lead_service import create_lead_for_appointment
                        lead_result = await create_lead_for_appointment(
                            db=db,
                            wa_id=wa_id,
                            customer=customer,
                            appointment_details=appointment_details,
                            lead_status="PENDING"
                        )
                        print(f"[lead_appointment_flow] DEBUG - Lead created: {lead_result}")
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
                    
                    return {
                        "status": "thank_you_sent", 
                        "appointment_details": appointment_details
                    }
                    
                except Exception as e:
                    print(f"[lead_appointment_flow] ERROR - Failed to send thank you message: {e}")
                    fallback_message = "✅ Thank you! We've noted your appointment details and our team will get back to you shortly. 😊"
                    await send_message_to_waid(wa_id, fallback_message, db)
                    
                    # Broadcast fallback message to WebSocket
                    try:
                        await manager.broadcast({
                            "from": "system",
                            "to": wa_id,
                            "type": "text",
                            "message": fallback_message,
                            "timestamp": datetime.now().isoformat(),
                            "meta": {"flow": "lead_appointment", "action": "thank_you_fallback"}
                        })
                        print(f"[lead_appointment_flow] DEBUG - Fallback thank you message broadcasted to WebSocket")
                    except Exception as ws_e:
                        print(f"[lead_appointment_flow] WARNING - WebSocket broadcast failed: {ws_e}")
                    
                    return {"status": "thank_you_fallback"}
            
            elif reply_id.startswith("time_") and (
                # Handle specific time formats: time_1630, time_10_00, time_14_00, etc.
                (len(reply_id) >= 8 and reply_id[5:].isdigit()) or  # time_1630 format
                (reply_id.count("_") >= 2 and reply_id.split("_")[2].isdigit())  # time_10_00 format
            ):
                # Specific time selection - send thank you message and create lead
                print(f"[lead_appointment_flow] DEBUG - Handling time selection: {reply_id}")
                
                try:
                    # Get appointment details from session for logging
                    appointment_details = {}
                    try:
                        from controllers.web_socket import lead_appointment_state
                        appointment_details = lead_appointment_state.get(wa_id, {})
                        print(f"[lead_appointment_flow] DEBUG - Appointment details: {appointment_details}")
                    except Exception as e:
                        print(f"[lead_appointment_flow] WARNING - Could not get appointment details: {e}")
                    
                    # Send thank you message
                    thank_you_message = "✅ Thank you! We've noted your appointment details and our team will get back to you shortly to confirm your appointment. 😊"
                    await send_message_to_waid(wa_id, thank_you_message, db)
                    
                    # Broadcast to WebSocket
                    try:
                        await manager.broadcast({
                            "from": "system",
                            "to": wa_id,
                            "type": "text",
                            "message": thank_you_message,
                            "timestamp": datetime.now().isoformat(),
                            "meta": {"flow": "lead_appointment", "action": "thank_you_sent"}
                        })
                        print(f"[lead_appointment_flow] DEBUG - Thank you message broadcasted to WebSocket")
                    except Exception as e:
                        print(f"[lead_appointment_flow] WARNING - WebSocket broadcast failed: {e}")
                    
                    # Create lead in Zoho (if integration is available)
                    try:
                        from .zoho_lead_service import create_lead_for_appointment
                        lead_result = await create_lead_for_appointment(
                            db=db,
                            wa_id=wa_id,
                            customer=customer,
                            appointment_details=appointment_details,
                            lead_status="PENDING"
                        )
                        print(f"[lead_appointment_flow] DEBUG - Lead created: {lead_result}")
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
                    
                    return {
                        "status": "thank_you_sent", 
                        "appointment_details": appointment_details
                    }
                    
                except Exception as e:
                    print(f"[lead_appointment_flow] ERROR - Failed to send thank you message: {e}")
                    fallback_message = "✅ Thank you! We've noted your appointment details and our team will get back to you shortly. 😊"
                    await send_message_to_waid(wa_id, fallback_message, db)
                    
                    # Broadcast fallback message to WebSocket
                    try:
                        await manager.broadcast({
                            "from": "system",
                            "to": wa_id,
                            "type": "text",
                            "message": fallback_message,
                            "timestamp": datetime.now().isoformat(),
                            "meta": {"flow": "lead_appointment", "action": "thank_you_fallback"}
                        })
                        print(f"[lead_appointment_flow] DEBUG - Fallback thank you message broadcasted to WebSocket")
                    except Exception as ws_e:
                        print(f"[lead_appointment_flow] WARNING - WebSocket broadcast failed: {ws_e}")
                    
                    return {"status": "thank_you_fallback"}
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
