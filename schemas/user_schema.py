from pydantic import BaseModel, EmailStr
from uuid import UUID
from enum import Enum

# Enum for user roles
class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    AGENT = "AGENT"

class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    phone_number: str
    role: UserRole = UserRole.AGENT  # default role

class UserCreate(UserBase):
    password: str  # plaintext (you should hash this before storing)

class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    password: str | None = None
    role: UserRole | None = None

class UserRead(UserBase):
    id: UUID

    class Config:
        from_attributes = True