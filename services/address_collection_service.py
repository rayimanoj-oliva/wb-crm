"""
Address Collection Service for WhatsApp Integration
Implements JioMart/Blinkit/Domino's style address collection
"""

from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime

from services.address_service import (
    create_customer_address, get_customer_addresses, get_customer_default_address,
    create_address_collection_session, update_address_collection_session,
    complete_address_collection_session, validate_address_data, process_location_address
)
from services.customer_service import get_customer_by_wa_id
from utils.address_templates import (
    get_order_confirmation_template, get_address_collection_options_template,
    get_location_request_template, get_manual_address_template,
    get_saved_addresses_template, get_address_confirmation_template,
    get_address_saved_template, get_address_error_template
)
from utils.whatsapp import send_message_to_waid
from utils.address_validator import extract_and_validate


class AddressCollectionService:
    """Service for managing address collection flow via WhatsApp"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def start_address_collection_after_order(
        self, 
        wa_id: str, 
        order_id: UUID, 
        customer_name: str, 
        order_total: float, 
        order_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Start address collection process after order placement
        Similar to JioMart's flow - send order confirmation with address button
        """
        try:
            # Get customer
            customer = get_customer_by_wa_id(self.db, wa_id)
            if not customer:
                raise ValueError("Customer not found")
            
            # Create address collection session
            session_data = {
                "customer_id": customer.id,
                "order_id": order_id,
                "collection_method": "pending"
            }
            session = create_address_collection_session(self.db, session_data)
            
            # Send order confirmation template with address button
            template = get_order_confirmation_template(customer_name, order_total, order_items)
            
            # Send the template message
            await self._send_template_message(wa_id, template)
            
            return {
                "success": True,
                "session_id": session.id,
                "message": "Address collection started"
            }
        
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def handle_address_button_click(
        self, 
        wa_id: str, 
        button_payload: str
    ) -> Dict[str, Any]:
        """
        Handle address collection button clicks
        """
        try:
            customer = get_customer_by_wa_id(self.db, wa_id)
            if not customer:
                raise ValueError("Customer not found")
            
            # Get active session
            session = self._get_active_session(customer.id)
            if not session:
                # Create new session if none exists
                session_data = {
                    "customer_id": customer.id,
                    "collection_method": "pending"
                }
                session = create_address_collection_session(self.db, session_data)
            
            if button_payload == "ADD_DELIVERY_ADDRESS":
                return await self._show_address_options(wa_id, customer, session)
            
            elif button_payload == "USE_CURRENT_LOCATION":
                return await self._request_location(wa_id, customer, session)
            
            elif button_payload == "ENTER_NEW_ADDRESS":
                return await self._request_manual_address(wa_id, customer, session)
            
            elif button_payload == "USE_SAVED_ADDRESS":
                return await self._show_saved_addresses(wa_id, customer, session)
            
            elif button_payload == "CONFIRM_ADDRESS":
                return await self._confirm_address(wa_id, customer, session)
            
            elif button_payload == "CHANGE_ADDRESS":
                return await self._show_address_options(wa_id, customer, session)
            
            elif button_payload == "RETRY_ADDRESS":
                return await self._request_manual_address(wa_id, customer, session)
            
            else:
                return {"success": False, "error": "Unknown button action"}
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def handle_location_message(
        self, 
        wa_id: str, 
        latitude: float, 
        longitude: float, 
        location_name: str = None, 
        location_address: str = None
    ) -> Dict[str, Any]:
        """
        Handle location sharing from customer
        """
        try:
            customer = get_customer_by_wa_id(self.db, wa_id)
            if not customer:
                raise ValueError("Customer not found")
            
            session = self._get_active_session(customer.id)
            if not session:
                raise ValueError("No active address collection session")
            
            # Process location address
            from schemas.address_schema import QuickAddressRequest
            request = QuickAddressRequest(
                customer_id=customer.id,
                latitude=latitude,
                longitude=longitude,
                location_name=location_name,
                location_address=location_address
            )
            
            address = process_location_address(self.db, request)
            if not address:
                raise ValueError("Failed to process location address")
            
            # Update session
            update_data = {
                "status": "collecting",
                "collection_method": "location",
                "session_data": {"address_id": str(address.id)}
            }
            update_address_collection_session(self.db, session.id, update_data)
            
            # Send confirmation template
            template = get_address_confirmation_template(address.__dict__)
            await self._send_template_message(wa_id, template)
            
            return {
                "success": True,
                "address_id": address.id,
                "message": "Location processed successfully"
            }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def handle_manual_address_text(
        self, 
        wa_id: str, 
        address_text: str
    ) -> Dict[str, Any]:
        """
        Handle manual address entry from customer
        """
        try:
            customer = get_customer_by_wa_id(self.db, wa_id)
            if not customer:
                raise ValueError("Customer not found")
            
            session = self._get_active_session(customer.id)
            if not session:
                raise ValueError("No active address collection session")
            
            # Validate address
            parsed_data, errors, suggestions = extract_and_validate(address_text)
            
            if errors:
                # Send error template
                error_message = "Please check your address format. Make sure to include: Name, House No, Area, City, State, Pincode"
                template = get_address_error_template(error_message)
                await self._send_template_message(wa_id, template)
                
                return {
                    "success": False,
                    "errors": errors,
                    "suggestions": suggestions
                }
            
            # Create address
            from schemas.address_schema import CustomerAddressCreate
            address_data = CustomerAddressCreate(
                customer_id=customer.id,
                full_name=parsed_data.get("FullName", ""),
                house_street=parsed_data.get("HouseStreet", ""),
                locality=parsed_data.get("Locality", ""),
                city=parsed_data.get("City", ""),
                state=parsed_data.get("State", ""),
                pincode=parsed_data.get("Pincode", ""),
                landmark=parsed_data.get("Landmark", ""),
                phone=parsed_data.get("Phone", customer.wa_id),
                address_type="home",
                is_default=True
            )
            
            address = create_customer_address(self.db, address_data)
            
            # Update session
            update_data = {
                "status": "collecting",
                "collection_method": "manual",
                "session_data": {"address_id": str(address.id)}
            }
            update_address_collection_session(self.db, session.id, update_data)
            
            # Send confirmation template
            template = get_address_confirmation_template(address.__dict__)
            await self._send_template_message(wa_id, template)
            
            return {
                "success": True,
                "address_id": address.id,
                "message": "Address processed successfully"
            }
        
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _show_address_options(self, wa_id: str, customer, session) -> Dict[str, Any]:
        """Show address collection options"""
        saved_addresses = get_customer_addresses(self.db, customer.id)
        has_saved = len(saved_addresses) > 0
        
        template = get_address_collection_options_template(customer.name or "Customer", has_saved)
        await self._send_template_message(wa_id, template)
        
        return {"success": True, "message": "Address options shown"}
    
    async def _request_location(self, wa_id: str, customer, session) -> Dict[str, Any]:
        """Request location from customer"""
        template = get_location_request_template()
        await self._send_template_message(wa_id, template)
        
        # Update session
        update_data = {
            "status": "collecting",
            "collection_method": "location"
        }
        update_address_collection_session(self.db, session.id, update_data)
        
        return {"success": True, "message": "Location request sent"}
    
    async def _request_manual_address(self, wa_id: str, customer, session) -> Dict[str, Any]:
        """Request manual address entry"""
        template = get_manual_address_template()
        await self._send_template_message(wa_id, template)
        
        # Update session
        update_data = {
            "status": "collecting",
            "collection_method": "manual"
        }
        update_address_collection_session(self.db, session.id, update_data)
        
        return {"success": True, "message": "Manual address request sent"}
    
    async def _show_saved_addresses(self, wa_id: str, customer, session) -> Dict[str, Any]:
        """Show saved addresses for selection"""
        saved_addresses = get_customer_addresses(self.db, customer.id)
        
        if not saved_addresses:
            # No saved addresses, redirect to manual entry
            return await self._request_manual_address(wa_id, customer, session)
        
        # Convert to dict format for template
        addresses_data = []
        for addr in saved_addresses:
            addresses_data.append({
                "id": str(addr.id),
                "house_street": addr.house_street,
                "locality": addr.locality,
                "city": addr.city,
                "pincode": addr.pincode
            })
        
        template = get_saved_addresses_template(addresses_data)
        await self._send_template_message(wa_id, template)
        
        return {"success": True, "message": "Saved addresses shown"}
    
    async def _confirm_address(self, wa_id: str, customer, session) -> Dict[str, Any]:
        """Confirm the selected address"""
        session_data = session.session_data or {}
        address_id = session_data.get("address_id")
        
        if not address_id:
            raise ValueError("No address to confirm")
        
        # Complete the session
        complete_address_collection_session(self.db, session.id, UUID(address_id))
        
        # Send confirmation
        template = get_address_saved_template()
        await self._send_template_message(wa_id, template)
        
        return {
            "success": True,
            "address_id": address_id,
            "message": "Address confirmed and saved"
        }
    
    def _get_active_session(self, customer_id: UUID):
        """Get active address collection session for customer"""
        from models.models import AddressCollectionSession
        return self.db.query(AddressCollectionSession).filter(
            AddressCollectionSession.customer_id == customer_id,
            AddressCollectionSession.status.in_(["pending", "collecting"])
        ).first()
    
    async def _send_template_message(self, wa_id: str, template: Dict[str, Any]):
        """Send template message to WhatsApp"""
        # This would integrate with your existing WhatsApp service
        # For now, we'll use the existing send_message_to_waid function
        message_text = f"Template: {template.get('template', {}).get('name', 'unknown')}"
        await send_message_to_waid(wa_id, message_text, self.db)
