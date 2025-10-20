from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta
import json

from models.models import CustomerAddress, AddressCollectionSession, Customer
from schemas.address_schema import (
    CustomerAddressCreate, CustomerAddressUpdate, AddressCollectionSessionCreate,
    AddressCollectionSessionUpdate, AddressValidationResponse, QuickAddressRequest,
    CustomerAddressBase
)
from utils.address_validator import extract_and_validate, validate_address_fields


def create_customer_address(db: Session, address_data: CustomerAddressCreate) -> CustomerAddress:
    """Create a new customer address"""
    # If this is set as default, unset other default addresses
    if address_data.is_default:
        db.query(CustomerAddress).filter(
            and_(
                CustomerAddress.customer_id == address_data.customer_id,
                CustomerAddress.is_default == True
            )
        ).update({"is_default": False})
    
    address = CustomerAddress(**address_data.dict())
    db.add(address)
    db.commit()
    db.refresh(address)
    return address


def get_customer_addresses(db: Session, customer_id: UUID) -> List[CustomerAddress]:
    """Get all addresses for a customer"""
    return db.query(CustomerAddress).filter(
        CustomerAddress.customer_id == customer_id
    ).order_by(CustomerAddress.is_default.desc(), CustomerAddress.created_at.desc()).all()


def get_customer_default_address(db: Session, customer_id: UUID) -> Optional[CustomerAddress]:
    """Get the default address for a customer"""
    return db.query(CustomerAddress).filter(
        and_(
            CustomerAddress.customer_id == customer_id,
            CustomerAddress.is_default == True
        )
    ).first()


def get_address_by_id(db: Session, address_id: UUID) -> Optional[CustomerAddress]:
    return db.query(CustomerAddress).filter(CustomerAddress.id == address_id).first()


def set_default_address(db: Session, customer_id: UUID, address_id: UUID) -> Optional[CustomerAddress]:
    """Mark one address as default and unset others for this customer."""
    address = db.query(CustomerAddress).filter(
        CustomerAddress.id == address_id,
        CustomerAddress.customer_id == customer_id,
    ).first()
    if not address:
        return None

    # Unset other defaults
    db.query(CustomerAddress).filter(
        CustomerAddress.customer_id == customer_id,
        CustomerAddress.id != address_id,
        CustomerAddress.is_default == True,
    ).update({"is_default": False})

    address.is_default = True
    db.commit()
    db.refresh(address)
    return address


def update_customer_address(db: Session, address_id: UUID, address_data: CustomerAddressUpdate) -> Optional[CustomerAddress]:
    """Update a customer address"""
    address = db.query(CustomerAddress).filter(CustomerAddress.id == address_id).first()
    if not address:
        return None
    
    # If setting as default, unset other defaults
    if address_data.is_default:
        db.query(CustomerAddress).filter(
            and_(
                CustomerAddress.customer_id == address.customer_id,
                CustomerAddress.is_default == True,
                CustomerAddress.id != address_id
            )
        ).update({"is_default": False})
    
    update_data = address_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(address, field, value)
    
    address.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(address)
    return address


def delete_customer_address(db: Session, address_id: UUID) -> bool:
    """Delete a customer address"""
    address = db.query(CustomerAddress).filter(CustomerAddress.id == address_id).first()
    if not address:
        return False
    
    db.delete(address)
    db.commit()
    return True


def create_address_collection_session(db: Session, session_data: AddressCollectionSessionCreate) -> AddressCollectionSession:
    """Create a new address collection session"""
    # Set expiration time (30 minutes from now)
    expires_at = datetime.utcnow() + timedelta(minutes=30)
    
    session = AddressCollectionSession(
        **session_data.dict(),
        expires_at=expires_at
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_address_collection_session(db: Session, session_id: UUID) -> Optional[AddressCollectionSession]:
    """Get an address collection session"""
    return db.query(AddressCollectionSession).filter(
        AddressCollectionSession.id == session_id
    ).first()


def update_address_collection_session(db: Session, session_id: UUID, update_data: AddressCollectionSessionUpdate) -> Optional[AddressCollectionSession]:
    """Update an address collection session"""
    session = db.query(AddressCollectionSession).filter(
        AddressCollectionSession.id == session_id
    ).first()
    if not session:
        return None
    
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(session, field, value)
    
    db.commit()
    db.refresh(session)
    return session


def complete_address_collection_session(db: Session, session_id: UUID, address_id: UUID) -> bool:
    """Complete an address collection session"""
    session = db.query(AddressCollectionSession).filter(
        AddressCollectionSession.id == session_id
    ).first()
    if not session:
        return False
    
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    session.session_data = {"address_id": str(address_id)}
    
    db.commit()
    return True


def cleanup_expired_sessions(db: Session) -> int:
    """Clean up expired address collection sessions"""
    expired_sessions = db.query(AddressCollectionSession).filter(
        and_(
            AddressCollectionSession.status.in_(["pending", "collecting"]),
            AddressCollectionSession.expires_at < datetime.utcnow()
        )
    ).all()
    
    count = len(expired_sessions)
    for session in expired_sessions:
        session.status = "cancelled"
    
    db.commit()
    return count


def validate_address_data(address_data: Dict[str, Any]) -> AddressValidationResponse:
    """Validate address data using the existing validator"""
    try:
        # Convert dict to string for validation
        address_text = f"""
        Full Name: {address_data.get('full_name', '')}
        House Street: {address_data.get('house_street', '')}
        Locality: {address_data.get('locality', '')}
        City: {address_data.get('city', '')}
        State: {address_data.get('state', '')}
        Pincode: {address_data.get('pincode', '')}
        Phone: {address_data.get('phone', '')}
        Landmark: {address_data.get('landmark', '')}
        """
        
        parsed_data, errors, suggestions = extract_and_validate(address_text)
        
        if not errors:
            # Convert parsed_data to CustomerAddressBase format
            try:
                validated_address = CustomerAddressBase(**parsed_data)
                return AddressValidationResponse(
                    is_valid=True,
                    errors=[],
                    suggestions=suggestions,
                    validated_address=validated_address
                )
            except Exception as e:
                return AddressValidationResponse(
                    is_valid=False,
                    errors=[f"Address format error: {str(e)}"],
                    suggestions=suggestions,
                    validated_address=None
                )
        else:
            return AddressValidationResponse(
                is_valid=False,
                errors=errors,
                suggestions=suggestions,
                validated_address=None
            )
    
    except Exception as e:
        return AddressValidationResponse(
            is_valid=False,
            errors=[f"Validation error: {str(e)}"],
            suggestions={},
            validated_address=None
        )


def process_location_address(db: Session, request: QuickAddressRequest) -> Optional[CustomerAddress]:
    """Process address from location data"""
    try:
        # For now, we'll create a basic address structure
        # In a real implementation, you'd use reverse geocoding APIs
        address_data = CustomerAddressCreate(
            customer_id=request.customer_id,
            full_name="Location Address",  # This should be filled from customer data
            house_street=request.location_address or "Shared Location",
            locality="Unknown",
            city="Unknown",
            state="Unknown",
            pincode="000000",  # This should be determined from location
            phone="0000000000",  # This should be filled from customer data
            latitude=request.latitude,
            longitude=request.longitude,
            address_type="other",
            is_default=False,
            is_verified=False
        )
        
        return create_customer_address(db, address_data)
    
    except Exception as e:
        print(f"Error processing location address: {e}")
        return None


def get_address_collection_options(db: Session, customer_id: UUID) -> Dict[str, Any]:
    """Get available address collection options for a customer"""
    saved_addresses = get_customer_addresses(db, customer_id)
    
    return {
        "saved_addresses": saved_addresses,
        "can_use_location": True,
        "has_saved_addresses": len(saved_addresses) > 0,
        "default_address": get_customer_default_address(db, customer_id)
    }
