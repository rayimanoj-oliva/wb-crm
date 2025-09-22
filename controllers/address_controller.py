from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID

from database.db import get_db
from services.address_service import (
    create_customer_address, get_customer_addresses, get_customer_default_address,
    update_customer_address, delete_customer_address, create_address_collection_session,
    get_address_collection_session, update_address_collection_session,
    complete_address_collection_session, validate_address_data, process_location_address,
    get_address_collection_options, cleanup_expired_sessions
)
from schemas.address_schema import (
    CustomerAddressCreate, CustomerAddressUpdate, CustomerAddressResponse,
    AddressCollectionSessionCreate, AddressCollectionSessionUpdate, AddressCollectionSessionResponse,
    AddressValidationRequest, AddressValidationResponse, QuickAddressRequest,
    AddressSelectionResponse
)

router = APIRouter(prefix="/address", tags=["address"])


@router.post("/", response_model=CustomerAddressResponse)
async def create_address(
    address_data: CustomerAddressCreate,
    db: Session = Depends(get_db)
):
    """Create a new customer address"""
    try:
        address = create_customer_address(db, address_data)
        return address
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create address: {str(e)}")


@router.get("/customer/{customer_id}", response_model=List[CustomerAddressResponse])
async def get_addresses(
    customer_id: UUID,
    db: Session = Depends(get_db)
):
    """Get all addresses for a customer"""
    addresses = get_customer_addresses(db, customer_id)
    return addresses


@router.get("/customer/{customer_id}/default", response_model=CustomerAddressResponse)
async def get_default_address(
    customer_id: UUID,
    db: Session = Depends(get_db)
):
    """Get the default address for a customer"""
    address = get_customer_default_address(db, customer_id)
    if not address:
        raise HTTPException(status_code=404, detail="No default address found")
    return address


@router.put("/{address_id}", response_model=CustomerAddressResponse)
async def update_address(
    address_id: UUID,
    address_data: CustomerAddressUpdate,
    db: Session = Depends(get_db)
):
    """Update a customer address"""
    address = update_customer_address(db, address_id, address_data)
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    return address


@router.delete("/{address_id}")
async def delete_address(
    address_id: UUID,
    db: Session = Depends(get_db)
):
    """Delete a customer address"""
    success = delete_customer_address(db, address_id)
    if not success:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"message": "Address deleted successfully"}


@router.post("/collection/session", response_model=AddressCollectionSessionResponse)
async def create_collection_session(
    session_data: AddressCollectionSessionCreate,
    db: Session = Depends(get_db)
):
    """Create a new address collection session"""
    try:
        session = create_address_collection_session(db, session_data)
        return session
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create session: {str(e)}")


@router.get("/collection/session/{session_id}", response_model=AddressCollectionSessionResponse)
async def get_collection_session(
    session_id: UUID,
    db: Session = Depends(get_db)
):
    """Get an address collection session"""
    session = get_address_collection_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.put("/collection/session/{session_id}", response_model=AddressCollectionSessionResponse)
async def update_collection_session(
    session_id: UUID,
    update_data: AddressCollectionSessionUpdate,
    db: Session = Depends(get_db)
):
    """Update an address collection session"""
    session = update_address_collection_session(db, session_id, update_data)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/collection/session/{session_id}/complete")
async def complete_collection_session(
    session_id: UUID,
    address_id: UUID,
    db: Session = Depends(get_db)
):
    """Complete an address collection session"""
    success = complete_address_collection_session(db, session_id, address_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session completed successfully"}


@router.post("/validate", response_model=AddressValidationResponse)
async def validate_address(
    request: AddressValidationRequest,
    db: Session = Depends(get_db)
):
    """Validate address data"""
    try:
        result = validate_address_data(request.address_data.dict())
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Validation failed: {str(e)}")


@router.post("/quick", response_model=CustomerAddressResponse)
async def create_quick_address(
    request: QuickAddressRequest,
    db: Session = Depends(get_db)
):
    """Create address from location or saved address"""
    try:
        if request.address_id:
            # Use saved address
            address = db.query(CustomerAddress).filter(
                CustomerAddress.id == request.address_id
            ).first()
            if not address:
                raise HTTPException(status_code=404, detail="Saved address not found")
            return address
        
        elif request.latitude and request.longitude:
            # Create from location
            address = process_location_address(db, request)
            if not address:
                raise HTTPException(status_code=400, detail="Failed to process location address")
            return address
        
        else:
            raise HTTPException(status_code=400, detail="Either address_id or location data required")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create quick address: {str(e)}")


@router.get("/options/{customer_id}", response_model=AddressSelectionResponse)
async def get_collection_options(
    customer_id: UUID,
    db: Session = Depends(get_db)
):
    """Get address collection options for a customer"""
    try:
        options = get_address_collection_options(db, customer_id)
        
        # Create a new session for this request
        session_data = AddressCollectionSessionCreate(
            customer_id=customer_id,
            collection_method="pending"
        )
        session = create_address_collection_session(db, session_data)
        
        return AddressSelectionResponse(
            saved_addresses=options["saved_addresses"],
            can_use_location=options["can_use_location"],
            session_id=session.id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to get options: {str(e)}")


@router.post("/cleanup")
async def cleanup_sessions(db: Session = Depends(get_db)):
    """Clean up expired address collection sessions"""
    try:
        count = cleanup_expired_sessions(db)
        return {"message": f"Cleaned up {count} expired sessions"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cleanup failed: {str(e)}")