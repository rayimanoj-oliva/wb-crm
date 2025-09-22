from pydantic import BaseModel, Field, validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime
import re


class CustomerAddressBase(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    house_street: str = Field(..., min_length=5, max_length=200)
    locality: str = Field(..., min_length=3, max_length=100)
    city: str = Field(..., min_length=2, max_length=50)
    state: str = Field(..., min_length=2, max_length=50)
    pincode: str = Field(..., min_length=6, max_length=6)
    landmark: Optional[str] = Field(None, max_length=100)
    phone: str = Field(..., min_length=10, max_length=15)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_type: str = Field(default="home", pattern="^(home|office|other)$")
    is_default: bool = False
    is_verified: bool = False

    @validator('pincode')
    def validate_pincode(cls, v):
        if not re.match(r'^[1-9][0-9]{5}$', v):
            raise ValueError('Invalid pincode format')
        return v

    @validator('phone')
    def validate_phone(cls, v):
        # Remove any non-digit characters
        phone = re.sub(r'\D', '', v)
        if len(phone) != 10:
            raise ValueError('Phone number must be 10 digits')
        return phone

    @validator('full_name')
    def validate_full_name(cls, v):
        if not re.match(r'^[A-Za-z\s]{2,100}$', v):
            raise ValueError('Invalid full name format')
        return v.strip()

    @validator('city')
    def validate_city(cls, v):
        if not re.match(r'^[A-Za-z\s]{2,50}$', v):
            raise ValueError('Invalid city format')
        return v.strip()

    @validator('state')
    def validate_state(cls, v):
        if not re.match(r'^[A-Za-z\s]{2,50}$', v):
            raise ValueError('Invalid state format')
        return v.strip()


class CustomerAddressCreate(CustomerAddressBase):
    customer_id: UUID


class CustomerAddressUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=100)
    house_street: Optional[str] = Field(None, min_length=5, max_length=200)
    locality: Optional[str] = Field(None, min_length=3, max_length=100)
    city: Optional[str] = Field(None, min_length=2, max_length=50)
    state: Optional[str] = Field(None, min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=6, max_length=6)
    landmark: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=15)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address_type: Optional[str] = Field(None, pattern="^(home|office|other)$")
    is_default: Optional[bool] = None
    is_verified: Optional[bool] = None


class CustomerAddressResponse(CustomerAddressBase):
    id: UUID
    customer_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AddressCollectionSessionCreate(BaseModel):
    customer_id: UUID
    order_id: Optional[UUID] = None
    collection_method: Optional[str] = Field(None, pattern="^(location|manual|saved)$")


class AddressCollectionSessionUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(pending|collecting|completed|cancelled)$")
    collection_method: Optional[str] = Field(None, pattern="^(location|manual|saved)$")
    session_data: Optional[dict] = None
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class AddressCollectionSessionResponse(BaseModel):
    id: UUID
    customer_id: UUID
    order_id: Optional[UUID]
    status: str
    collection_method: Optional[str]
    session_data: Optional[dict]
    created_at: datetime
    expires_at: Optional[datetime]
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


class AddressCollectionRequest(BaseModel):
    """Request for starting address collection process"""
    customer_id: UUID
    order_id: Optional[UUID] = None
    method: str = Field(..., pattern="^(location|manual|saved)$")


class AddressValidationRequest(BaseModel):
    """Request for validating address data"""
    address_data: CustomerAddressBase


class AddressValidationResponse(BaseModel):
    """Response for address validation"""
    is_valid: bool
    errors: List[str] = []
    suggestions: dict = {}
    validated_address: Optional[CustomerAddressBase] = None


class QuickAddressRequest(BaseModel):
    """Request for quick address entry from location or saved address"""
    customer_id: UUID
    address_id: Optional[UUID] = None  # For saved address
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None


class AddressSelectionResponse(BaseModel):
    """Response for address selection options"""
    saved_addresses: List[CustomerAddressResponse] = []
    can_use_location: bool = True
    session_id: UUID
