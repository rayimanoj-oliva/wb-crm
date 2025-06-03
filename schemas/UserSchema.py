from pydantic import BaseModel, EmailStr
from uuid import UUID

class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    phone_number: str

class UserCreate(UserBase):
    password: str  # plaintext (you should hash this before storing)

class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone_number: str | None = None
    password: str | None = None

class UserRead(UserBase):
    id: UUID

    class Config:
        orm_mode = True


