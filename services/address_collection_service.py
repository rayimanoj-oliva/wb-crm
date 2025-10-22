from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from datetime import datetime
import json

from models.models import Customer, CustomerAddress
from schemas.address_schema import CustomerAddressCreate
from services.address_service import create_customer_address
from services.customer_service import get_or_create_customer
from schemas.customer_schema import CustomerCreate


class AddressCollectionService:
    def __init__(self, db: Session):
        self.db = db

    async def handle_location_message(
        self, 
        wa_id: str, 
        latitude: float, 
        longitude: float, 
        location_name: str = "", 
        location_address: str = ""
    ) -> Dict[str, Any]:
        """Handle location messages for address collection"""
        try:
            # Get or create customer
            customer = get_or_create_customer(self.db, CustomerCreate(wa_id=wa_id, name=""))
            
            # Create address from location
            address_data = CustomerAddressCreate(
                customer_id=customer.id,
                full_name="Location Address",
                house_street=location_address or "Shared Location",
                locality="Unknown",
                city="Unknown", 
                state="Unknown",
                pincode="000000",
                phone="0000000000",
                latitude=latitude,
                longitude=longitude,
                address_type="other",
                is_default=False,
                is_verified=False
            )
            
            address = create_customer_address(self.db, address_data)
            
            return {
                "success": True,
                "address_id": str(address.id),
                "message": "Address saved from location"
            }
            
        except Exception as e:
            print(f"Error in handle_location_message: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def handle_flow_response(
        self, 
        wa_id: str, 
        flow_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle WhatsApp flow response for address collection"""
        try:
            # Get or create customer
            customer = get_or_create_customer(self.db, CustomerCreate(wa_id=wa_id, name=""))
            
            # Extract and validate address data
            address_data = self._extract_address_data(flow_data)
            
            if not self._validate_required_fields(address_data):
                return {
                    "success": False,
                    "error": "Missing required address fields"
                }
            
            # Create address
            address_create = CustomerAddressCreate(
                customer_id=customer.id,
                full_name=address_data.get("full_name", ""),
                house_street=address_data.get("house_street", ""),
                locality=address_data.get("locality", ""),
                city=address_data.get("city", ""),
                state=address_data.get("state", ""),
                pincode=address_data.get("pincode", ""),
                phone=address_data.get("phone_number", ""),
                address_type="home",
                is_default=True,
                is_verified=False
            )
            
            address = create_customer_address(self.db, address_create)
            
            return {
                "success": True,
                "address_id": str(address.id),
                "message": "Address saved successfully"
            }
            
        except Exception as e:
            print(f"Error in handle_flow_response: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    def _extract_address_data(self, flow_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract address data from flow response with comprehensive field mapping"""
        address_data = {}
        
        # Comprehensive field mappings for different flow configurations
        field_mappings = {
            "full_name": [
                "full_name", "name", "customer_name", "fullname", 
                "customer_full_name", "user_name", "contact_name"
            ],
            "phone_number": [
                "phone_number", "phone", "mobile", "mobile_number",
                "contact_number", "phone_no", "telephone", "contact_phone"
            ],
            "house_street": [
                "house_street", "address_line_1", "street", "address_line",
                "house_number", "street_address", "address1", "line1"
            ],
            "locality": [
                "locality", "area", "neighborhood", "sector", "block"
            ],
            "city": [
                "city", "town", "municipality", "district"
            ],
            "state": [
                "state", "province", "region"
            ],
            "pincode": [
                "pincode", "postal_code", "zip_code", "zipcode", "postcode"
            ],
            "landmark": [
                "landmark", "nearby", "reference_point", "landmark_nearby"
            ]
        }
        
        # Extract data using field mappings
        for field_name, possible_keys in field_mappings.items():
            for key in possible_keys:
                if key in flow_data and flow_data[key]:
                    address_data[field_name] = str(flow_data[key]).strip()
                    break
        
        # Also check for nested data structures
        if not address_data.get("full_name"):
            # Check for nested contact info
            if "contact" in flow_data:
                contact = flow_data["contact"]
                if isinstance(contact, dict):
                    for key in ["name", "full_name", "customer_name"]:
                        if key in contact and contact[key]:
                            address_data["full_name"] = str(contact[key]).strip()
                            break
        
        # Check for address object
        if "address" in flow_data:
            address_obj = flow_data["address"]
            if isinstance(address_obj, dict):
                for field_name, possible_keys in field_mappings.items():
                    if not address_data.get(field_name):
                        for key in possible_keys:
                            if key in address_obj and address_obj[key]:
                                address_data[field_name] = str(address_obj[key]).strip()
                                break
        
        print(f"[AddressCollectionService] Extracted address data: {address_data}")
        return address_data

    def _validate_required_fields(self, address_data: Dict[str, Any]) -> bool:
        """Validate that required fields are present"""
        required_fields = ["full_name", "phone_number", "pincode", "house_street"]
        
        for field in required_fields:
            if not address_data.get(field):
                print(f"[AddressCollectionService] Missing required field: {field}")
                return False
        
        return True
