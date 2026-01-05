from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from enum import Enum
from typing import Optional
from schemas.organization_schema import OrganizationResponse

# Enum for user roles (legacy support)
class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    ORG_ADMIN = "ORG_ADMIN"  # Added for compatibility with new role system
    AGENT = "AGENT"

class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    phone_number: str
    role: UserRole = UserRole.AGENT  # Legacy role enum (for backward compatibility)
    organization_id: Optional[UUID] = Field(None, description="Organization ID - required for ORG_ADMIN and AGENT, must be None for SUPER_ADMIN")
    role_id: Optional[UUID] = Field(None, description="Role ID from roles table (SUPER_ADMIN, ORG_ADMIN, AGENT)")

class UserCreate(UserBase):
    password: str  # plaintext (you should hash this before storing)

class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    password: str | None = None
    role: UserRole | None = None  # Legacy role enum
    organization_id: Optional[UUID] = None
    role_id: Optional[UUID] = None

class UserRead(UserBase):
    id: UUID
    organization: Optional[OrganizationResponse] = None  # Include organization object

    class Config:
        from_attributes = True