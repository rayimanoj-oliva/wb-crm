from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import os
import re
import json
import requests
from sqlalchemy.orm import Session

from config.constants import get_messages_url
from services import message_service, order_service
from services.whatsapp_service import get_latest_token
from schemas.message_schema import MessageCreate
from utils.whatsapp import send_message_to_waid
from utils.ws_manager import manager


async def _send_payment_redirect_button(wa_id: str, payment_url: str, order_id: str, db: Session) -> None:
    """Send an interactive message with a direct payment link button for better UX"""
    try:
        from services.whatsapp_service import get_latest_token
        from config.constants import get_messages_url
        import os
        import requests
        
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            return

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        # Create interactive message with payment redirect button
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "header": {
                    "type": "text",
                    "text": "💳 Complete Payment"
                },
                "body": {
                    "text": f"Order #{order_id}\n\nClick the button below to redirect to Razorpay's secure payment page:"
                },
                "footer": {
                    "text": "Secure payment powered by Razorpay"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {
                                "id": "redirect_to_payment",
                                "title": "🔗 Pay Now"
                            }
                        },
                        {
                            "type": "reply",
                            "reply": {
                                "id": "payment_help",
                                "title": "❓ Help"
                            }
                        }
                    ]
                }
            }
        }

        response = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        
        if response.status_code == 200:
            print(f"[payment_redirect_button] Payment redirect button sent successfully")
            
            # Store the payment URL for the redirect_to_payment button handler
            # We'll handle this in the button reply processing
            try:
                from utils.ws_manager import manager
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "Complete Payment - Click the button below to redirect to Razorpay's secure payment page:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {
                        "kind": "payment_redirect",
                        "payment_url": payment_url,
                        "order_id": order_id
                    }
                })
            except Exception as e:
                print(f"[payment_redirect_button] WebSocket broadcast failed: {e}")
        else:
            print(f"[payment_redirect_button] Failed to send payment redirect button: {response.text}")
            
    except Exception as e:
        print(f"[payment_redirect_button] Error sending payment redirect button: {e}")


async def run_interactive_type(
    db: Session,
    *,
    message: Dict[str, Any],
    interactive: Dict[str, Any],
    i_type: str,
    timestamp: datetime,
    message_id: str,
    from_wa_id: str,
    to_wa_id: str,
    wa_id: str,
    customer: Any,
) -> Dict[str, Any]:
    """Handle WhatsApp interactive payloads (flow, form, button_reply, list_reply).

    Returns a status dict. If not handled, returns {"status": "skipped"}.
    """
    
    print(f"[interactive_type] DEBUG - run_interactive_type called for {wa_id}, i_type={i_type}")
    if i_type == "list_reply":
        reply_id = interactive.get("list_reply", {}).get("id", "")
        print(f"[interactive_type] DEBUG - list_reply with id: {reply_id}")

    # 1) Flow submission (e.g., address collection)
    if i_type == "flow":
        flow_response = interactive.get("flow_response", {})
        flow_id = (flow_response.get("flow_id", "") or "")
        flow_cta = flow_response.get("flow_cta", "")
        flow_action_payload = flow_response.get("flow_action_payload", {})

        try:
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "flow_response",
                "flow_id": flow_id,
                "flow_cta": flow_cta,
                "payload": flow_action_payload,
                "timestamp": timestamp.isoformat(),
            })
        except Exception:
            pass

        if (flow_id == "address_collection_flow") or (flow_id == "1314521433687006") or ("address" in flow_id.lower()):
            print(f"[flow_handler] DEBUG - Processing address flow: {flow_id}")
            print(f"[flow_handler] DEBUG - Flow payload: {flow_action_payload}")
            try:
                    # Use flow data directly without complex mapping
                    address_data: Dict[str, Any] = {}
                    if flow_action_payload:
                        print(f"[flow_handler] DEBUG - Flow action payload received: {flow_action_payload}")
                        print(f"[flow_handler] DEBUG - Flow action payload keys: {list(flow_action_payload.keys())}")
                    
                    # Simple direct mapping - use flow data as-is
                    address_data = {
                        "full_name": flow_action_payload.get("name") or flow_action_payload.get("full_name", ""),
                        "phone_number": flow_action_payload.get("phone") or flow_action_payload.get("phone_number", ""),
                        "house_street": flow_action_payload.get("address_line") or flow_action_payload.get("house_street", ""),
                        "locality": flow_action_payload.get("locality", ""),
                        "city": flow_action_payload.get("city", ""),
                        "state": flow_action_payload.get("state", ""),
                        "pincode": flow_action_payload.get("pincode", ""),
                        "landmark": flow_action_payload.get("landmark", "")
                    }
                    
                    # Clean up empty strings
                    address_data = {k: v.strip() if v else "" for k, v in address_data.items()}
                    
                    # Also check for nested data structures
                    if not address_data.get("full_name"):
                        # Check for nested contact info
                        if "contact" in flow_action_payload:
                            contact = flow_action_payload["contact"]
                            if isinstance(contact, dict):
                                for key in ["name", "full_name", "customer_name"]:
                                    if key in contact and contact[key]:
                                        address_data["full_name"] = str(contact[key]).strip()
                                        break
                    
                    # Check for address object
                    if "address" in flow_action_payload:
                        address_obj = flow_action_payload["address"]
                        if isinstance(address_obj, dict):
                            for field_name, possible_keys in field_mappings.items():
                                if not address_data.get(field_name):
                                    for key in possible_keys:
                                        if key in address_obj and address_obj[key]:
                                            address_data[field_name] = str(address_obj[key]).strip()
                                            break
                    
                    # Validate & save - check for required fields from your flow
                    print(f"[flow_handler] DEBUG - Extracted address data: {address_data}")
                    print(f"[flow_handler] DEBUG - Raw flow payload keys: {list(flow_action_payload.keys()) if flow_action_payload else 'None'}")
                    print(f"[flow_handler] DEBUG - Raw flow payload values: {flow_action_payload}")
                    print(f"[flow_handler] DEBUG - Address data keys: {list(address_data.keys())}")
                    print(f"[flow_handler] DEBUG - Address data values: {list(address_data.values())}")
                    
                    # Enhanced debugging for flow data extraction
                    try:
                        from controllers.web_socket import debug_flow_data_extraction
                        debug_flow_data_extraction(flow_action_payload, address_data)
                    except Exception as e:
                        print(f"[flow_handler] DEBUG - Could not run flow debug: {e}")
                    
                    # ---------------- Normalization for literal placeholders ----------------
                    try:
                        literal_keys = {
                            "full_name": {"full_name", "name"},
                            "phone_number": {"phone", "phone_number", "mobile"},
                            "house_street": {"address", "address_line", "house_street", "street"},
                            "city": {"city"},
                            "state": {"state"},
                            "pincode": {"pincode", "postal_code", "zipcode", "zip_code", "postcode"},
                        }
                        def _is_literal(value: str, keys: set[str]) -> bool:
                            v = str(value or "").strip().lower()
                            return (v in keys) or (v.startswith("{{") and v.endswith("}}")) or (v.startswith("$") and len(v) <= 32)

                        # Null-out literal echoes so we can apply fallbacks reliably
                        for field, keys in literal_keys.items():
                            if field in address_data and _is_literal(address_data.get(field), keys):
                                print(f"[flow_handler] INFO - Normalizing literal value for {field}: {address_data.get(field)}")
                                address_data[field] = ""
                    except Exception as e:
                        print(f"[flow_handler] DEBUG - Normalization error: {e}")
                    
                    # Check if we have any actual data
                    has_data = any(value and str(value).strip() for value in address_data.values())
                    print(f"[flow_handler] DEBUG - Has any data: {has_data}")
                    
                    if not has_data:
                        print(f"[flow_handler] WARNING - No data extracted from flow response!")
                        print(f"[flow_handler] WARNING - This might indicate a flow configuration issue or data extraction problem")
                        await send_message_to_waid(wa_id, "❌ No data received from the form. Please check your flow configuration.", db)
                        return {"status": "no_data_extracted", "flow_payload": flow_action_payload}
                    
                    required_fields = ["full_name", "phone_number", "pincode", "house_street"]
                    missing_fields = [field for field in required_fields if not address_data.get(field)]
                    print(f"[flow_handler] DEBUG - Missing required fields: {missing_fields}")
                    
                    # If we have some data but missing required fields, try alternative extraction
                    if missing_fields and any(address_data.values()):
                        print(f"[flow_handler] DEBUG - Attempting alternative field extraction...")
                        # Try to extract from any remaining keys in the payload
                        for key, value in flow_action_payload.items():
                            if isinstance(value, str) and value.strip():
                                # Try to match by content patterns
                                value_lower = value.lower().strip()
                                if any(name_word in value_lower for name_word in ["name", "full"]):
                                    if not address_data.get("full_name"):
                                        address_data["full_name"] = value.strip()
                                        print(f"[flow_handler] DEBUG - Found name in key '{key}': {value}")
                                elif any(phone_word in value_lower for phone_word in ["phone", "mobile", "contact"]):
                                    if not address_data.get("phone_number"):
                                        address_data["phone_number"] = value.strip()
                                        print(f"[flow_handler] DEBUG - Found phone in key '{key}': {value}")
                                elif any(addr_word in value_lower for addr_word in ["address", "street", "house"]):
                                    if not address_data.get("house_street"):
                                        address_data["house_street"] = value.strip()
                                        print(f"[flow_handler] DEBUG - Found address in key '{key}': {value}")
                                elif value.isdigit() and len(value) == 6:
                                    if not address_data.get("pincode"):
                                        address_data["pincode"] = value.strip()
                                        print(f"[flow_handler] DEBUG - Found pincode in key '{key}': {value}")
                        
                        # Re-check missing fields after alternative extraction
                        missing_fields = [field for field in required_fields if not address_data.get(field)]
                        print(f"[flow_handler] DEBUG - Missing fields after alternative extraction: {missing_fields}")
                    
                    # Final validation with fallbacks
                    if not address_data.get("phone_number") and customer and hasattr(customer, 'wa_id'):
                        # Use customer's WA ID as phone fallback
                        wa_digits = ''.join(filter(str.isdigit, str(customer.wa_id)))
                        if len(wa_digits) >= 10:
                            address_data["phone_number"] = wa_digits[-10:]
                            print(f"[flow_handler] DEBUG - Using WA ID as phone fallback: {address_data['phone_number']}")

                    # Ensure full_name is non-empty and valid-ish
                    if not address_data.get("full_name"):
                        # Try contact name or default Client
                        contact_name = None
                        try:
                            contact = flow_action_payload.get("contact") if isinstance(flow_action_payload, dict) else None
                            if isinstance(contact, dict):
                                contact_name = contact.get("name") or contact.get("full_name")
                        except Exception:
                            contact_name = None
                        address_data["full_name"] = (contact_name or "Client").strip()
                        print(f"[flow_handler] DEBUG - full_name fallback applied: {address_data['full_name']}")

                    # Ensure house_street has minimum length
                    if not address_data.get("house_street") or len(address_data.get("house_street", "").strip()) < 5:
                        address_data["house_street"] = "Address not provided"
                        print(f"[flow_handler] DEBUG - house_street fallback applied")

                    # Ensure city/state
                    if not address_data.get("city"):
                        address_data["city"] = "Unknown"
                    if not address_data.get("state"):
                        address_data["state"] = "Unknown"

                    # Ensure pincode: prefer 6-digit; fallback to valid default (starts 1-9)
                    if not address_data.get("pincode") or not str(address_data.get("pincode")).isdigit() or len(str(address_data.get("pincode"))) != 6 or str(address_data.get("pincode"))[0] == "0":
                        address_data["pincode"] = "500001"
                        print(f"[flow_handler] DEBUG - pincode fallback applied: {address_data['pincode']}")
                    
                    if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode") and address_data.get("house_street"):
                        from schemas.address_schema import CustomerAddressCreate
                        from services.address_service import create_customer_address

                        # Construct enhanced address with floor/tower info
                        house_street = address_data.get("house_street", "")
                        floor_number = address_data.get("floor_number", "")
                        tower_number = address_data.get("tower_number", "")
                        
                        # Combine address line with floor/tower if available
                        if floor_number or tower_number:
                            additional_info = []
                            if floor_number:
                                additional_info.append(f"Floor {floor_number}")
                            if tower_number:
                                additional_info.append(f"Tower {tower_number}")
                            house_street = f"{house_street}, {', '.join(additional_info)}"
                        
                        # Use city and state directly
                        city_val = address_data.get("city") or "Unknown"
                        state_val = address_data.get("state") or "Unknown"

                        # Sanitize phone: ensure 10 digits; fallback to WA ID
                        try:
                            import re as _re
                            # Try both "phone" and "phone_number" field names
                            phone_source = address_data.get("phone") or address_data.get("phone_number") or customer.wa_id or ""
                            phone_digits = _re.sub(r"\D", "", str(phone_source))
                            if len(phone_digits) >= 10:
                                phone_final = phone_digits[-10:]
                            else:
                                wa_digits = _re.sub(r"\D", "", str(customer.wa_id or ""))
                                phone_final = wa_digits[-10:] if len(wa_digits) >= 10 else (phone_digits + ("0" * (10 - len(phone_digits))))[:10]
                            print(f"[flow_handler] DEBUG - Phone processing: source={phone_source}, digits={phone_digits}, final={phone_final}")
                        except Exception as e:
                            print(f"[flow_handler] DEBUG - Phone processing error: {e}")
                            phone_final = (str(customer.wa_id)[-10:] if customer and getattr(customer, 'wa_id', None) else "0000000000")
                        
                        # Normalize pincode to 6 digits if possible (keep as-is if already valid)
                        try:
                            import re as _re2
                            pin_src = address_data.get("pincode", "")
                            print(f"[flow_handler] DEBUG - Pincode processing: source={pin_src}")
                            
                            # If pincode is the literal string "pincode", it means the flow is not configured correctly
                            if pin_src == "pincode":
                                print(f"[flow_handler] WARNING - Pincode field contains literal string 'pincode' - flow configuration issue")
                                pincode_final = "000000"  # Default fallback
                            else:
                                pin_digits = _re2.sub(r"\D", "", str(pin_src))
                                pincode_final = pin_digits[:6] if len(pin_digits) >= 6 else pin_digits
                                print(f"[flow_handler] DEBUG - Pincode processing: digits={pin_digits}, final={pincode_final}")
                        except Exception as e:
                            print(f"[flow_handler] DEBUG - Pincode processing error: {e}")
                            pincode_final = "000000"  # Default fallback
                        
                        print(f"[flow_handler] DEBUG - Creating address with: full_name={address_data.get('full_name', '')}, house_street={house_street}, locality={city_val}, city={city_val}, state={state_val}, pincode={pincode_final}, phone={phone_final}")
                        
                        try:
                            address_create = CustomerAddressCreate(
                                customer_id=customer.id,
                                full_name=address_data.get("full_name", ""),
                                house_street=house_street,
                                locality=city_val,  # Use city as locality fallback
                                city=city_val,
                                state=state_val,
                                pincode=pincode_final,
                                landmark=address_data.get("landmark", ""),
                                phone=phone_final,
                                address_type="home",
                                is_default=True,
                            )
                            print(f"[flow_handler] DEBUG - AddressCreate object created successfully")
                            print(f"[flow_handler] DEBUG - AddressCreate data: {address_create.dict()}")
                            
                            # Validate required fields before saving
                            required_fields = ["customer_id", "full_name", "house_street", "city", "pincode", "phone"]
                            missing_fields = []
                            for field in required_fields:
                                value = getattr(address_create, field, None)
                                if not value or (isinstance(value, str) and not value.strip()):
                                    missing_fields.append(field)
                            
                            if missing_fields:
                                print(f"[flow_handler] ERROR - Missing required fields: {missing_fields}")
                                await send_message_to_waid(wa_id, f"❌ Missing required information: {', '.join(missing_fields)}. Please fill the form completely.", db)
                                return {"status": "missing_fields", "missing_fields": missing_fields}
                            
                            saved_address = create_customer_address(db, address_create)
                            print(f"[flow_handler] DEBUG - Address saved successfully with ID: {saved_address.id}")
                            print(f"[flow_handler] DEBUG - Saved address details: {saved_address.__dict__}")

                            # Notify customer on successful save
                            await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                            await send_message_to_waid(
                                wa_id,
                                f"📍 {saved_address.full_name}, {saved_address.phone}, {saved_address.house_street}, {saved_address.city}, {saved_address.state} - {saved_address.pincode}",
                                db,
                            )

                            # Clear awaiting address flag if present (best-effort; ignore if missing)
                            try:
                                from controllers.web_socket import awaiting_address_users  # type: ignore
                                awaiting_address_users[wa_id] = False
                            except Exception:
                                pass

                            # Continue with payment flow (best-effort)
                            try:
                                latest_order = (
                                    db.query(order_service.Order)
                                    .filter(order_service.Order.customer_id == customer.id)
                                    .order_by(order_service.Order.timestamp.desc())
                                    .first()
                                )
                                total_amount = 0
                                if latest_order:
                                    for item in latest_order.items:
                                        qty = item.quantity or 1
                                        price = item.item_price or item.price or 0
                                        total_amount += float(price) * int(qty)
                                if total_amount > 0:
                                    from utils.razorpay_utils import create_razorpay_payment_link
                                    try:
                                        payment_resp = create_razorpay_payment_link(
                                            amount=float(total_amount),
                                            currency="INR",
                                            description=f"WA Order {str(latest_order.id) if latest_order else ''}",
                                        )
                                        pay_link = payment_resp.get("short_url") if isinstance(payment_resp, dict) else None
                                        if pay_link:
                                            await send_message_to_waid(wa_id, f"💳 Please complete your payment using this link: {pay_link}", db)
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                            return {"status": "address_saved", "message_id": message_id}

                        except Exception as e:
                            print(f"[flow_handler] ERROR - Failed to create address: {e}")
                            print(f"[flow_handler] ERROR - Exception type: {type(e).__name__}")
                            print(f"[flow_handler] ERROR - Address data: {address_data}")
                            await send_message_to_waid(wa_id, f"❌ Error saving address: {str(e)}. Please try again.", db)
                            return {"status": "address_creation_failed", "error": str(e)}
                    else:
                        print(f"[flow_handler] DEBUG - Missing required fields, attempting partial save")
                        print(f"[flow_handler] DEBUG - Available data: {address_data}")
                        print(f"[flow_handler] DEBUG - Flow payload structure: {json.dumps(flow_action_payload, indent=2) if flow_action_payload else 'None'}")

                        # Attempt a partial save with sensible defaults and embed raw payload in landmark
                        try:
                            from schemas.address_schema import CustomerAddressCreate as _AddrCreate
                            from services.address_service import create_customer_address as _create_addr
                            raw_short = ""  # keep landmark concise
                            try:
                                raw_short = json.dumps(flow_action_payload)[:400]
                            except Exception:
                                raw_short = str(flow_action_payload)[:400]

                            partial = _AddrCreate(
                                customer_id=customer.id,
                                full_name=(address_data.get("full_name") or "Client").strip(),
                                house_street=(address_data.get("house_street") or "Address not provided").strip(),
                                locality=(address_data.get("locality") or address_data.get("city") or "Unknown").strip(),
                                city=(address_data.get("city") or "Unknown").strip(),
                                state=(address_data.get("state") or "Unknown").strip(),
                                pincode=(address_data.get("pincode") or "000000").strip(),
                                landmark=((address_data.get("landmark") or "") + (f" | Raw: {raw_short}" if raw_short else ""))[:255],
                                phone=(address_data.get("phone_number") or str(getattr(customer, 'wa_id', '') or "0000000000")[-10:]).strip(),
                                address_type="home",
                                is_default=True,
                            )
                            saved_partial = _create_addr(db, partial)
                            print(f"[flow_handler] WARN - Saved partial address with ID: {saved_partial.id}")

                            await send_message_to_waid(wa_id, "✅ Address saved with available details.", db)
                            await send_message_to_waid(
                                wa_id,
                                f"📍 {partial.full_name}, {partial.house_street}, {partial.city} - {partial.pincode}",
                                db,
                            )
                            await send_message_to_waid(wa_id, "ℹ️ You can update any missing details anytime.", db)

                            return {"status": "address_saved_partial", "message_id": message_id, "missing_fields": missing_fields}
                        except Exception as e:
                            print(f"[flow_handler] ERROR - Partial save failed: {e}")

                            # Send more specific error message and resend form as fallback
                            missing_list = [field.replace('_', ' ').title() for field in missing_fields]
                            error_msg = f"❌ Please fill in all required fields. Missing: {', '.join(missing_list)}"
                            await send_message_to_waid(wa_id, error_msg, db)

                            try:
                                from controllers.web_socket import _send_address_flow_directly
                                await _send_address_flow_directly(wa_id, db, customer_id=customer.id)
                            except Exception as e2:
                                print(f"[flow_handler] DEBUG - Failed to resend address form: {e2}")

                            return {"status": "flow_incomplete", "message_id": message_id}
            except Exception as e:
                print(f"[flow_handler] ERROR - Exception in address processing: {str(e)}")
                print(f"[flow_handler] ERROR - Exception type: {type(e).__name__}")
                import traceback
                print(f"[flow_handler] ERROR - Traceback: {traceback.format_exc()}")
                await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                return {"status": "flow_error", "message_id": message_id}

        return {"status": "flow_processed", "message_id": message_id}

    # 2) Form submission (address_form)
    if i_type == "form":
        form_response = interactive.get("form_response", {})
        form_name = form_response.get("name", "")
        form_data = form_response.get("data", [])
        if form_name == "address_form":
            try:
                address_data: Dict[str, Any] = {}
                for item in form_data:
                    field_id = item.get("id", "")
                    field_value = item.get("value", "")
                    address_data[field_id] = field_value

                if address_data.get("full_name") and address_data.get("phone_number") and address_data.get("pincode"):
                    from schemas.address_schema import CustomerAddressCreate
                    from services.address_service import create_customer_address

                    address_create = CustomerAddressCreate(
                        customer_id=customer.id,
                        full_name=address_data.get("full_name", ""),
                        house_street=address_data.get("house_street", ""),
                        locality=address_data.get("locality", ""),
                        city=address_data.get("city", ""),
                        state=address_data.get("state", ""),
                        pincode=address_data.get("pincode", ""),
                        landmark=address_data.get("landmark", ""),
                        phone=address_data.get("phone_number", customer.wa_id),
                        address_type="home",
                        is_default=True,
                    )
                    saved_address = create_customer_address(db, address_create)

                    await send_message_to_waid(wa_id, "✅ Address saved successfully!", db)
                    await send_message_to_waid(
                        wa_id,
                        f"📍 {saved_address.full_name}, {saved_address.phone}, {saved_address.house_street}, {saved_address.city}, {saved_address.state} - {saved_address.pincode}",
                        db,
                    )

                    # Clear awaiting address flag if present
                    try:
                        from controllers.web_socket import awaiting_address_users  # type: ignore
                        awaiting_address_users[wa_id] = False
                    except Exception:
                        pass

                    # Generate payment link using enhanced service
                    try:
                        from services.cart_checkout_service import CartCheckoutService
                        checkout_service = CartCheckoutService(db)
                        
                        # Get latest order for this customer
                        latest_order = (
                            db.query(order_service.Order)
                            .filter(order_service.Order.customer_id == customer.id)
                            .order_by(order_service.Order.timestamp.desc())
                            .first()
                        )
                        
                        if latest_order:
                            # Generate payment link with comprehensive order details
                            payment_result = await checkout_service.generate_payment_link_for_order(
                                order_id=str(latest_order.id),
                                customer_wa_id=wa_id,
                                customer_name=getattr(customer, "name", None),
                                customer_email=getattr(customer, "email", None),
                                customer_phone=getattr(customer, "phone", None)
                            )
                            
                            if payment_result.get("success"):
                                print(f"[address_form] Payment link generated successfully for order {latest_order.id}")
                            else:
                                print(f"[address_form] Payment generation failed: {payment_result.get('error')}")
                                await send_message_to_waid(wa_id, "❌ Unable to generate payment link. Please try again.", db)
                        else:
                            await send_message_to_waid(wa_id, "❌ No order found. Please add items to your cart first.", db)
                    except Exception as e:
                        print(f"[address_form] Payment flow error: {e}")
                        await send_message_to_waid(wa_id, "❌ Payment processing failed. Please try again.", db)

                    return {"status": "address_saved", "message_id": message_id}
                else:
                    await send_message_to_waid(wa_id, "❌ Please fill in all required fields (Name, Phone, Pincode, House & Street, Area, City, State).", db)
                    return {"status": "form_incomplete", "message_id": message_id}
            except Exception:
                await send_message_to_waid(wa_id, "❌ Error processing your address. Please try again.", db)
                return {"status": "form_error", "message_id": message_id}

        # Not an address form; let caller handle further
        return {"status": "skipped"}

    # 3) Persist button/list replies early and delegate treatment buttons to existing flow
    try:
        if i_type in {"button_reply", "list_reply"}:
            title = interactive.get("button_reply", {}).get("title") if i_type == "button_reply" else interactive.get("list_reply", {}).get("title")
            reply_id = interactive.get("button_reply", {}).get("id") if i_type == "button_reply" else interactive.get("list_reply", {}).get("id")
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
            await manager.broadcast({
                "from": from_wa_id,
                "to": to_wa_id,
                "type": "interactive",
                "message": reply_text_any,
                "timestamp": timestamp.isoformat(),
            })

            # 3a) Appointment week/day flow
            try:
                # Step 1: book appointment -> send week list
                if (reply_id or "").strip().lower() == "book_appointment" or (title or "").strip().lower() in {"book an appointment", "book appointment"}:
                    sent = await _send_week_list(db=db, wa_id=wa_id)
                    if sent.get("success"):
                        return {"status": "week_list_sent", "message_id": message_id}
                    # No legacy fallback
                    return {"status": "failed_to_send_week_list", "message_id": message_id}

                # Step 2: week selected -> send day list
                if i_type == "list_reply" and (reply_id or "").lower().startswith("week_"):
                    # id format: week_YYYY-MM-DD_YYYY-MM-DD (start_end)
                    try:
                        parts = (reply_id or "").split("_")
                        if len(parts) == 3:
                            # older format week_start_end without underscores in dates isn't used; expect 3 parts
                            pass
                        if len(parts) >= 3:
                            start_end = parts[1:]
                            start_iso = start_end[0]
                            end_iso = start_end[1] if len(start_end) > 1 else start_end[0]
                            sent_days = await _send_day_list_for_week(db=db, wa_id=wa_id, start_iso=start_iso, end_iso=end_iso)
                            if sent_days.get("success"):
                                return {"status": "week_selected", "message_id": message_id}
                    except Exception:
                        pass

                # Step 3: date picked -> confirm and send time buttons
                if i_type == "list_reply" and (reply_id or "").lower().startswith("date_"):
                    try:
                        # CHECKPOINT: Check if user is in lead appointment flow
                        # If yes, skip this treatment flow logic and let lead appointment flow handle it
                        try:
                            from controllers.web_socket import lead_appointment_state
                            if wa_id in lead_appointment_state and lead_appointment_state[wa_id]:
                                print(f"[interactive_type] DEBUG - User {wa_id} is in lead appointment flow, skipping treatment flow date handling")
                                return {"status": "skipped"}  # Let lead appointment flow handle it
                        except Exception as e:
                            print(f"[interactive_type] WARNING - Could not check lead appointment state: {e}")
                        
                        date_iso = (reply_id or "")[5:]
                        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_iso):
                            # Persist selected date and ask for time
                            from controllers.web_socket import appointment_state  # local import
                            appointment_state[wa_id] = {"date": date_iso}
                            from utils.whatsapp import send_message_to_waid as _send_txt
                            await _send_txt(wa_id, f"✅ Date selected: {date_iso}", db)
                            # Ask for time categories (morning/afternoon/evening)
                            sent_slots = await _send_time_slot_categories(db=db, wa_id=wa_id)
                            if sent_slots.get("success"):
                                return {"status": "date_selected", "message_id": message_id}
                            return {"status": "failed_to_send_time_categories", "message_id": message_id}
                    except Exception:
                        pass

                # Step 4: time category picked -> send times list for that slot
                if i_type == "list_reply" and (reply_id or "").lower().startswith("slot_"):
                    # Treatment flow handles slot selections
                    # Lead appointment flow will skip these if user is not in lead flow
                    print(f"[interactive_type] DEBUG - Treatment flow handling slot selection: {reply_id}")
                    
                    # e.g., slot_morning, slot_afternoon, slot_evening
                    slot_id = (reply_id or "").lower().strip()
                    sent_times = await _send_times_for_slot(db=db, wa_id=wa_id, slot_id=slot_id)
                    if sent_times.get("success"):
                        return {"status": "slot_selected", "message_id": message_id}

                # Step 5: exact time picked -> confirm appointment
                if i_type == "list_reply" and (reply_id or "").lower().startswith("time_"):
                    # Treatment flow handles time selections
                    # Lead appointment flow will skip these if user is not in lead flow
                    print(f"[interactive_type] DEBUG - Treatment flow handling time selection: {reply_id}")
                    
                    # Map id time_HH_MM to label like 09:00 AM
                    parts = (reply_id or "").split("_")
                    if len(parts) == 3:
                        hh = int(parts[1])
                        mm = int(parts[2])
                        dt = datetime(2000, 1, 1, hh, mm)
                        time_label = dt.strftime("%I:%M %p").lstrip("0")
                    else:
                        # Fallback to title
                        time_label = title or ""
                    if time_label:
                        from controllers.web_socket import appointment_state, _confirm_appointment  # type: ignore
                        date_iso = (appointment_state.get(wa_id) or {}).get("date")
                        print(f"[interactive_type] DEBUG - Treatment flow time selection: wa_id={wa_id}, date_iso={date_iso}, time_label={time_label}")
                        if date_iso:
                            print(f"[interactive_type] DEBUG - Calling _confirm_appointment for treatment flow")
                            result = await _confirm_appointment(wa_id, db, date_iso, time_label)
                            print(f"[interactive_type] DEBUG - _confirm_appointment result: {result}")
                            return {"status": "appointment_captured", "message_id": message_id}
                        else:
                            # Ask for date first (restart)
                            print(f"[interactive_type] DEBUG - No date found, asking for date first")
                            await send_message_to_waid(wa_id, "Please select a date first.", db)
                            await _send_week_list(db=db, wa_id=wa_id)
                            return {"status": "need_date_first", "message_id": message_id}
            except Exception:
                pass

            # Handle dummy payment button responses
            try:
                if reply_id == "test_payment_link":
                    await send_message_to_waid(
                        wa_id, 
                        "🧪 Test payment link sent above! Click it to test the payment flow.", 
                        db
                    )
                    return {"status": "test_payment_info_sent", "message_id": message_id}
                
                elif reply_id == "dummy_payment_info":
                    info_message = """ℹ️ **Test Payment Information**

This is a dummy payment system for testing:

✅ **What it does:**
• Generates test payment links
• Simulates payment flow
• No real money charged
• Tests cart checkout process

✅ **How to use:**
• Click the test payment link
• Complete the test payment flow
• Verify order processing works

✅ **Benefits:**
• Safe testing environment
• No financial risk
• Full flow testing
• Development friendly

Happy testing! 🚀"""
                    
                    await send_message_to_waid(wa_id, info_message, db)
                    return {"status": "dummy_info_sent", "message_id": message_id}
            except Exception as e:
                print(f"[dummy_payment_buttons] Error handling dummy payment buttons: {e}")
                pass

            # Handle payment link button responses
            try:
                if reply_id == "view_payment_link":
                    # User wants to see payment link - retrieve and send the actual payment link
                    try:
                        # Get the latest order for this customer
                        latest_order = (
                            db.query(order_service.Order)
                            .filter(order_service.Order.customer_id == customer.id)
                            .order_by(order_service.Order.timestamp.desc())
                            .first()
                        )
                        
                        if latest_order:
                            # Get the payment record for this order
                            from models.models import Payment
                            payment_record = (
                                db.query(Payment)
                                .filter(Payment.order_id == latest_order.id)
                                .order_by(Payment.created_at.desc())
                                .first()
                            )
                            
                            if payment_record and payment_record.razorpay_short_url:
                                # Send the actual payment link with instructions
                                payment_message = f"""🔗 **Payment Link Ready!**

Click the link below to complete your payment securely:

{payment_record.razorpay_short_url}

**Payment Details:**
• Order ID: {latest_order.id}
• Amount: ₹{payment_record.amount:.2f}
• Status: {payment_record.status}

This link will redirect you to Razorpay's secure payment page where you can complete your transaction using UPI, cards, or net banking.

💡 **Tip:** The link is valid for 30 minutes. If it expires, please request a new payment link."""
                                
                                await send_message_to_waid(wa_id, payment_message, db)
                                
                                # Also send an interactive message with a direct link button for better UX
                                await _send_payment_redirect_button(wa_id, payment_record.razorpay_short_url, latest_order.id, db)
                                
                                return {"status": "payment_link_sent", "message_id": message_id}
                            else:
                                # No payment link found, create a new one
                                await send_message_to_waid(wa_id, "🔄 Creating a new payment link for you...", db)
                                
                                from services.cart_checkout_service import CartCheckoutService
                                checkout_service = CartCheckoutService(db)
                                
                                result = await checkout_service.generate_payment_link_for_order(
                                    order_id=str(latest_order.id),
                                    customer_wa_id=wa_id,
                                    customer_name=getattr(customer, "name", None),
                                    customer_email=getattr(customer, "email", None),
                                    customer_phone=getattr(customer, "phone", None)
                                )
                                
                                if result.get("success"):
                                    await send_message_to_waid(wa_id, "✅ New payment link created and sent above!", db)
                                    return {"status": "new_payment_link_created", "message_id": message_id}
                                else:
                                    await send_message_to_waid(wa_id, "❌ Unable to create payment link. Please try again later.", db)
                                    return {"status": "payment_link_creation_failed", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ No active order found. Please add items to your cart first.", db)
                            return {"status": "no_order_found", "message_id": message_id}
                            
                    except Exception as e:
                        print(f"[payment_link_handler] Error retrieving payment link: {e}")
                        await send_message_to_waid(wa_id, "❌ Unable to retrieve payment link. Please try again later.", db)
                        return {"status": "payment_link_error", "message_id": message_id}
                
                elif reply_id == "redirect_to_payment":
                    # User clicked "Pay Now" button - send the payment link for immediate redirection
                    try:
                        # Get the latest order for this customer
                        latest_order = (
                            db.query(order_service.Order)
                            .filter(order_service.Order.customer_id == customer.id)
                            .order_by(order_service.Order.timestamp.desc())
                            .first()
                        )
                        
                        if latest_order:
                            # Get the payment record for this order
                            from models.models import Payment
                            payment_record = (
                                db.query(Payment)
                                .filter(Payment.order_id == latest_order.id)
                                .order_by(Payment.created_at.desc())
                                .first()
                            )
                            
                            if payment_record and payment_record.razorpay_short_url:
                                # Send immediate payment redirection message
                                redirect_message = f"""🚀 **Redirecting to Payment...**

Click the link below to complete your payment:

{payment_record.razorpay_short_url}

**Quick Payment Info:**
• Order: #{latest_order.id}
• Amount: ₹{payment_record.amount:.2f}
• Payment Gateway: Razorpay

This will open Razorpay's secure payment page where you can pay using:
• UPI (PhonePe, Google Pay, Paytm)
• Credit/Debit Cards
• Net Banking
• Wallets

✅ **Secure & Fast Payment** - Complete in under 2 minutes!"""
                                
                                await send_message_to_waid(wa_id, redirect_message, db)
                                return {"status": "payment_redirect_sent", "message_id": message_id}
                            else:
                                await send_message_to_waid(wa_id, "❌ Payment link not found. Please request a new payment link.", db)
                                return {"status": "payment_link_not_found", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ No active order found. Please add items to your cart first.", db)
                            return {"status": "no_order_found", "message_id": message_id}
                            
                    except Exception as e:
                        print(f"[payment_redirect_handler] Error handling payment redirect: {e}")
                        await send_message_to_waid(wa_id, "❌ Unable to redirect to payment. Please try again.", db)
                        return {"status": "payment_redirect_error", "message_id": message_id}
                
                elif reply_id == "order_details":
                    # User wants to see order details
                    try:
                        latest_order = (
                            db.query(order_service.Order)
                            .filter(order_service.Order.customer_id == customer.id)
                            .order_by(order_service.Order.timestamp.desc())
                            .first()
                        )
                        
                        if latest_order:
                            from services.cart_checkout_service import CartCheckoutService
                            checkout_service = CartCheckoutService(db)
                            order_summary = checkout_service.get_order_summary_for_payment(str(latest_order.id))
                            
                            details_message = f"""📋 **Order Details**

Order ID: {latest_order.id}
Status: Pending Payment
Items: {order_summary.get('items_count', 0)}
Total: {order_summary.get('formatted_total', 'N/A')}
Created: {latest_order.timestamp.strftime('%d %B %Y, %H:%M')}

Please complete your payment to confirm this order."""
                            
                            await send_message_to_waid(wa_id, details_message, db)
                        else:
                            await send_message_to_waid(wa_id, "❌ No order found.", db)
                    except Exception as e:
                        print(f"[order_details] Error: {e}")
                        await send_message_to_waid(wa_id, "❌ Unable to fetch order details.", db)
                    
                    return {"status": "order_details_sent", "message_id": message_id}
                
                elif reply_id == "help_payment":
                    # User needs help with payment
                    help_message = """❓ **Payment Help**

🔗 **How to Pay:**
1. Click the payment link sent above
2. Complete payment on Razorpay
3. You'll receive confirmation

💳 **Payment Methods:**
• UPI (Google Pay, PhonePe, Paytm)
• Credit/Debit Cards
• Net Banking
• Wallets

⏰ **Payment Validity:**
• Link expires in 30 minutes
• Complete payment to confirm order

🆘 **Need More Help?**
Contact us for assistance with your payment."""
                    
                    await send_message_to_waid(wa_id, help_message, db)
                    return {"status": "payment_help_sent", "message_id": message_id}
            except Exception as e:
                print(f"[payment_buttons] Error handling payment buttons: {e}")
                pass

            # Handle address selection (buttons or list) first
            try:
                if reply_id in ["use_saved_address", "add_new_address"] or (reply_id or "").startswith("use_address_"):
                    from controllers.web_socket import _send_address_form_directly
                    from services.address_service import get_customer_default_address, get_address_by_id, set_default_address
                    
                    # Using a specific address from list (use_address_<uuid>)
                    if (reply_id or "").startswith("use_address_"):
                        try:
                            addr_id = (reply_id or "")[12:]
                            selected = get_address_by_id(db, addr_id)
                        except Exception:
                            selected = None
                        if selected and getattr(selected, "customer_id", None) == getattr(customer, "id", None):
                            # Optionally set as default for convenience
                            try:
                                set_default_address(db, customer.id, selected.id)
                            except Exception:
                                pass
                            await send_message_to_waid(wa_id, "✅ Using your selected address!", db)
                            await send_message_to_waid(
                                wa_id,
                                f"📍 {selected.full_name}, {selected.phone}, {selected.house_street}, {selected.city}, {selected.state} - {selected.pincode}",
                                db,
                            )
                            # Continue with payment flow using enhanced service
                            try:
                                from services.cart_checkout_service import CartCheckoutService
                                checkout_service = CartCheckoutService(db)
                                
                                # Get latest order for this customer
                                latest_order = (
                                    db.query(order_service.Order)
                                    .filter(order_service.Order.customer_id == customer.id)
                                    .order_by(order_service.Order.timestamp.desc())
                                    .first()
                                )
                                
                                if latest_order:
                                    # Generate payment link with comprehensive order details
                                    payment_result = await checkout_service.generate_payment_link_for_order(
                                        order_id=str(latest_order.id),
                                        customer_wa_id=wa_id,
                                        customer_name=getattr(customer, "name", None),
                                        customer_email=getattr(customer, "email", None),
                                        customer_phone=getattr(customer, "phone", None)
                                    )
                                    
                                    if payment_result.get("success"):
                                        print(f"[address_selection] Payment link generated successfully for order {latest_order.id}")
                                    else:
                                        print(f"[address_selection] Payment generation failed: {payment_result.get('error')}")
                                        await send_message_to_waid(wa_id, "❌ Unable to generate payment link. Please try again.", db)
                                else:
                                    await send_message_to_waid(wa_id, "❌ No order found. Please add items to your cart first.", db)
                            except Exception as e:
                                print(f"[address_selection] Payment flow error: {e}")
                                await send_message_to_waid(wa_id, "❌ Payment processing failed. Please try again.", db)
                            return {"status": "saved_address_used", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ Address not found. Please add a new address.", db)
                            await _send_address_form_directly(wa_id, db, customer_id=customer.id)
                            return {"status": "address_form_sent", "message_id": message_id}

                    if reply_id == "use_saved_address":
                        # Backward-compatible: use default address
                        default_address = get_customer_default_address(db, customer.id)
                        if default_address:
                            await send_message_to_waid(wa_id, "✅ Using your saved address!", db)
                            await send_message_to_waid(
                                wa_id,
                                f"📍 {default_address.full_name}, {default_address.house_street}, {default_address.city} - {default_address.pincode}",
                                db,
                            )
                            
                            # Continue with payment flow using enhanced service
                            try:
                                from services.cart_checkout_service import CartCheckoutService
                                checkout_service = CartCheckoutService(db)
                                
                                # Get latest order for this customer
                                latest_order = (
                                    db.query(order_service.Order)
                                    .filter(order_service.Order.customer_id == customer.id)
                                    .order_by(order_service.Order.timestamp.desc())
                                    .first()
                                )
                                
                                if latest_order:
                                    # Generate payment link with comprehensive order details
                                    payment_result = await checkout_service.generate_payment_link_for_order(
                                        order_id=str(latest_order.id),
                                        customer_wa_id=wa_id,
                                        customer_name=getattr(customer, "name", None),
                                        customer_email=getattr(customer, "email", None),
                                        customer_phone=getattr(customer, "phone", None)
                                    )
                                    
                                    if payment_result.get("success"):
                                        print(f"[address_selection] Payment link generated successfully for order {latest_order.id}")
                                    else:
                                        print(f"[address_selection] Payment generation failed: {payment_result.get('error')}")
                                        await send_message_to_waid(wa_id, "❌ Unable to generate payment link. Please try again.", db)
                                else:
                                    await send_message_to_waid(wa_id, "❌ No order found. Please add items to your cart first.", db)
                            except Exception as e:
                                print(f"[address_selection] Payment flow error: {e}")
                                await send_message_to_waid(wa_id, "❌ Payment processing failed. Please try again.", db)
                            
                            return {"status": "saved_address_used", "message_id": message_id}
                        else:
                            await send_message_to_waid(wa_id, "❌ No saved address found. Please add a new address.", db)
                            await _send_address_form_directly(wa_id, db, customer_id=customer.id)
                            return {"status": "address_form_sent", "message_id": message_id}
                    
                    elif reply_id == "add_new_address":
                        # User wants to add new address - send address form
                        await send_message_to_waid(wa_id, "📝 Please provide your new address details.", db)
                        await _send_address_form_directly(wa_id, db, customer_id=customer.id)
                        return {"status": "address_form_sent", "message_id": message_id}
                        
            except Exception as e:
                print(f"[address_selection] ERROR - Exception in address selection: {str(e)}")
                pass

            # Handle cart next actions (modify/cancel/proceed) first
            try:
                from controllers.components.products_flow import handle_cart_next_action  # type: ignore
                cart_result = await handle_cart_next_action(
                    db,
                    wa_id=wa_id,
                    reply_id=(reply_id or ""),
                    customer=customer,
                )
                if (cart_result or {}).get("status") in {"modify_catalog_sent", "catalog_link_sent", "order_cancel_ack", "address_template_sent", "address_prompt_sent"}:
                    return cart_result
            except Exception:
                pass

            # Delegate skin/hair/body and next actions
            from controllers.components.treament_flow import run_treatment_buttons_flow  # local import to avoid cycles
            flow_result = await run_treatment_buttons_flow(
                db,
                wa_id=wa_id,
                to_wa_id=to_wa_id,
                message_id=message_id,
                btn_id=reply_id,
                btn_text=title,
            )
            if (flow_result or {}).get("status") in {"list_sent", "hair_template_sent", "body_template_sent", "next_actions_sent"}:
                return flow_result

            # Delegate appointment buttons (book, callback, time)
            from controllers.components.treament_flow import run_appointment_buttons_flow  # type: ignore
            appt_result = await run_appointment_buttons_flow(
                db,
                wa_id=wa_id,
                btn_id=reply_id,
                btn_text=title,
            )
            if (appt_result or {}).get("status") in {"date_list_sent", "callback_ack", "appointment_captured", "need_date_first"}:
                return appt_result
    except Exception:
        pass

    return {"status": "skipped"}


def _format_week_label(start: datetime, end: datetime) -> str:
    try:
        # Examples: "Oct 14–20", "Oct 28–Nov 3"
        start_label = start.strftime("%b %d").lstrip("0")
        if start.month == end.month:
            end_label = end.strftime("%d").lstrip("0")
            return f"{start.strftime('%b')} {start.strftime('%d').lstrip('0')}–{end_label}"
        else:
            return f"{start.strftime('%b')} {start.strftime('%d').lstrip('0')}–{end.strftime('%b')} {end.strftime('%d').lstrip('0')}"
    except Exception:
        return f"{start.strftime('%b %d')}–{end.strftime('%b %d')}"


def _generate_week_ranges(num_weeks: int = 4) -> list[dict]:
    try:
        today = datetime.now().date()
        weeks = []
        # Start from today; build consecutive 7-day windows
        start_date = today
        for _ in range(num_weeks):
            end_date = start_date + timedelta(days=6)
            label = _format_week_label(datetime.combine(start_date, datetime.min.time()), datetime.combine(end_date, datetime.min.time()))
            weeks.append({
                "id": f"week_{start_date.strftime('%Y-%m-%d')}_{end_date.strftime('%Y-%m-%d')}",
                "title": label,
            })
            start_date = end_date + timedelta(days=1)
        return weeks
    except Exception:
        return []


def _generate_days_for_range(start_iso: str, end_iso: str) -> list[dict]:
    try:
        start = datetime.strptime(start_iso, "%Y-%m-%d").date()
        end = datetime.strptime(end_iso, "%Y-%m-%d").date()
        if end < start:
            start, end = end, start
        rows = []
        cur = start
        while cur <= end:
            # Skip past dates (only future or today+)
            if cur >= datetime.now().date():
                rows.append({
                    "id": f"date_{cur.strftime('%Y-%m-%d')}",
                    "title": datetime.strftime(datetime.combine(cur, datetime.min.time()), "%a, %b %d").replace(" 0", " ")
                })
            cur += timedelta(days=1)
        return rows
    except Exception:
        return []


async def _send_week_list(*, db: Session, wa_id: str) -> Dict[str, Any]:
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Unable to fetch appointment weeks right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = _generate_week_ranges(4)
        if not rows:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ No weeks available. Please try again later.", db)
            return {"success": False}

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "📅 Please choose your appointment week:"},
                "action": {
                    "button": "Choose Week",
                    "sections": [
                        {"title": "Available Weeks", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "📅 Please choose your appointment week:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Weeks"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Could not send week options. Please try again.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        from utils.whatsapp import send_message_to_waid as _send_txt
        await _send_txt(wa_id, f"❌ Error sending week options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def _send_day_list_for_week(*, db: Session, wa_id: str, start_iso: str, end_iso: str) -> Dict[str, Any]:
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Unable to fetch days right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = _generate_days_for_range(start_iso, end_iso)
        if not rows:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ No days available in this week. Please choose another week.", db)
            return {"success": False}

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "🗓️ Pick a date:"},
                "action": {
                    "button": "Pick Day",
                    "sections": [
                        {"title": "Available Days", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "🗓️ Pick a date:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Days"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Could not send day options. Please try again.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        from utils.whatsapp import send_message_to_waid as _send_txt
        await _send_txt(wa_id, f"❌ Error sending day options: {str(e)}", db)
        return {"success": False, "error": str(e)}


# Public wrapper to be used by other modules (e.g., webhook) to kick off week selection
async def send_week_list(db: Session, wa_id: str) -> Dict[str, Any]:
    return await _send_week_list(db=db, wa_id=wa_id)


def _generate_time_rows_for_slot(slot_id: str) -> list[dict]:
    try:
        slot_id = (slot_id or "").lower().strip()
        print(f"DEBUG: Processing slot_id: '{slot_id}'")  # Debug log
        
        slot_intervals: dict[str, list[str]] = {
            "slot_morning": [
                "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", "11:00 AM", "11:30 AM"
            ],
            "slot_afternoon": [
                "12:00 PM", "12:30 PM", "01:00 PM", "01:30 PM", "02:00 PM",
                "02:30 PM", "03:00 PM", "03:30 PM", "04:00 PM", "04:30 PM"
            ],
            "slot_evening": [
                "05:00 PM", "05:30 PM", "06:00 PM", "06:30 PM", "07:00 PM"
            ],
        }
        times = slot_intervals.get(slot_id, [])
        print(f"DEBUG: Found times for slot '{slot_id}': {times}")  # Debug log
        
        rows: list[dict] = []
        for label in times:
            # Parse 12-hour label to 24h components for id
            try:
                dt = datetime.strptime(label, "%I:%M %p")
                hh = dt.strftime("%H")
                mm = dt.strftime("%M")
            except Exception:
                # Fallback: strip non-digits, best-effort
                import re as _re
                parts = _re.findall(r"(\d{1,2}):(\d{2})", label)
                if parts:
                    hh, mm = parts[0]
                else:
                    continue
            rows.append({"id": f"time_{hh}_{mm}", "title": label})
        
        print(f"DEBUG: Generated {len(rows)} rows for slot '{slot_id}'")  # Debug log
        return rows
    except Exception as e:
        print(f"DEBUG: Exception in _generate_time_rows_for_slot: {e}")  # Debug log
        return []


async def _send_time_slot_categories(*, db: Session, wa_id: str) -> Dict[str, Any]:
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to fetch time slots right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        # Keep titles short to satisfy WhatsApp limits (<=24 chars recommended for row titles)
        rows = [
            {"id": "slot_morning", "title": "Morning (9–11 AM)"},
            {"id": "slot_afternoon", "title": "Afternoon (12–4 PM)"},
            {"id": "slot_evening", "title": "Evening (5–7 PM)"},
        ]

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": "Time Slots"},
                "body": {"text": "⏰ Choose a time slot category:"},
                "action": {
                    "button": "Choose Slot",
                    "sections": [
                        {"title": "Time Slots", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "⏰ Choose a time slot category:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Time Slots"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            try:
                err_txt = resp.text
            except Exception:
                err_txt = ""
            await send_message_to_waid(wa_id, "❌ Could not send time slot categories.", db)
            try:
                import logging
                logging.getLogger(__name__).error("Time slot categories send failed: %s", err_txt)
            except Exception:
                pass
            return {"success": False, "error": resp.text}
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending time slot categories: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def _send_times_for_slot(*, db: Session, wa_id: str, slot_id: str) -> Dict[str, Any]:
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to fetch times right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = _generate_time_rows_for_slot(slot_id)
        if not rows:
            await send_message_to_waid(wa_id, "❌ No times available in this slot.", db)
            return {"success": False}

        section_title = (
            "Morning" if slot_id == "slot_morning" else (
                "Afternoon" if slot_id == "slot_afternoon" else "Evening"
            )
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": f"{section_title} Times"},
                "body": {"text": f"⏱️ Pick a time in {section_title} Slot:"},
                "action": {
                    "button": "Pick Time",
                    "sections": [
                        {"title": f"{section_title} Times", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": f"⏱️ Pick a time in {section_title} Slot:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": f"{section_title} Times"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            try:
                err_txt = resp.text
            except Exception:
                err_txt = ""
            await send_message_to_waid(wa_id, "❌ Could not send times.", db)
            try:
                import logging
                logging.getLogger(__name__).error("Time list send failed for %s: %s", section_title, err_txt)
            except Exception:
                pass
            return {"success": False, "error": resp.text}
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending times: {str(e)}", db)
        return {"success": False, "error": str(e)}


# =============================================================================
# LEAD APPOINTMENT FLOW - TIME SELECTION FUNCTIONS
# =============================================================================

async def _send_lead_week_list(*, db: Session, wa_id: str) -> Dict[str, Any]:
    """Send week list specifically for lead appointment flow.
    
    This function is used ONLY within the lead appointment flow context.
    """
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Unable to fetch appointment weeks right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = _generate_week_ranges(4)
        if not rows:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ No weeks available. Please try again later.", db)
            return {"success": False}

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "📅 Please choose your preferred week for the appointment:"},
                "action": {
                    "button": "Choose Week",
                    "sections": [
                        {"title": "Available Weeks", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "📅 Please choose your preferred week for the appointment:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Weeks", "flow": "lead_appointment"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Could not send week options. Please try again.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        from utils.whatsapp import send_message_to_waid as _send_txt
        await _send_txt(wa_id, f"❌ Error sending week options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def _send_lead_day_list_for_week(*, db: Session, wa_id: str, start_iso: str, end_iso: str) -> Dict[str, Any]:
    """Send day list for lead appointment flow."""
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Unable to fetch days right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = _generate_days_for_range(start_iso, end_iso)
        if not rows:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ No days available in this week. Please choose another week.", db)
            return {"success": False}

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "🗓️ Select your preferred date:"},
                "action": {
                    "button": "Pick Date",
                    "sections": [
                        {"title": "Available Dates", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "🗓️ Select your preferred date:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Available Dates", "flow": "lead_appointment"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            from utils.whatsapp import send_message_to_waid as _send_txt
            await _send_txt(wa_id, "❌ Could not send date options. Please try again.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        from utils.whatsapp import send_message_to_waid as _send_txt
        await _send_txt(wa_id, f"❌ Error sending date options: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def _send_lead_time_slot_categories(*, db: Session, wa_id: str) -> Dict[str, Any]:
    """Send time slot categories for lead appointment flow."""
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to fetch time slots right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = [
            {"id": "slot_morning", "title": "Morning (9–11 AM)"},
            {"id": "slot_afternoon", "title": "Afternoon (12–4 PM)"},
            {"id": "slot_evening", "title": "Evening (5–7 PM)"},
        ]

        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": "Time Slots"},
                "body": {"text": "⏰ Choose your preferred time slot:"},
                "action": {
                    "button": "Choose Slot",
                    "sections": [
                        {"title": "Time Slots", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": "⏰ Choose your preferred time slot:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": "Time Slots", "flow": "lead_appointment"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send time slot categories.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending time slot categories: {str(e)}", db)
        return {"success": False, "error": str(e)}


async def _send_lead_times_for_slot(*, db: Session, wa_id: str, slot_id: str) -> Dict[str, Any]:
    """Send times for a specific slot in lead appointment flow."""
    try:
        token_entry = get_latest_token(db)
        if not token_entry or not token_entry.token:
            await send_message_to_waid(wa_id, "❌ Unable to fetch times right now.", db)
            return {"success": False}

        access_token = token_entry.token
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        phone_id = os.getenv("WHATSAPP_PHONE_ID", "367633743092037")

        rows = _generate_time_rows_for_slot(slot_id)
        if not rows:
            await send_message_to_waid(wa_id, "❌ No times available in this slot.", db)
            return {"success": False}

        section_title = (
            "Morning" if slot_id == "slot_morning" else (
                "Afternoon" if slot_id == "slot_afternoon" else "Evening"
            )
        )
        payload = {
            "messaging_product": "whatsapp",
            "to": wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {"type": "text", "text": f"{section_title} Times"},
                "body": {"text": f"⏱️ Pick your preferred time in {section_title}:"},
                "action": {
                    "button": "Pick Time",
                    "sections": [
                        {"title": f"{section_title} Times", "rows": rows}
                    ]
                }
            }
        }

        resp = requests.post(get_messages_url(phone_id), headers=headers, json=payload)
        if resp.status_code == 200:
            try:
                await manager.broadcast({
                    "from": os.getenv("WHATSAPP_DISPLAY_NUMBER", "917729992376"),
                    "to": wa_id,
                    "type": "interactive",
                    "message": f"⏱️ Pick your preferred time in {section_title}:",
                    "timestamp": datetime.now().isoformat(),
                    "meta": {"kind": "list", "section": f"{section_title} Times", "flow": "lead_appointment"}
                })
            except Exception:
                pass
            return {"success": True}
        else:
            await send_message_to_waid(wa_id, "❌ Could not send times.", db)
            return {"success": False, "error": resp.text}
    except Exception as e:
        await send_message_to_waid(wa_id, f"❌ Error sending times: {str(e)}", db)
        return {"success": False, "error": str(e)}


# Public wrapper for lead appointment flow
async def send_lead_week_list(db: Session, wa_id: str) -> Dict[str, Any]:
    """Public wrapper for lead appointment week list."""
    return await _send_lead_week_list(db=db, wa_id=wa_id)
