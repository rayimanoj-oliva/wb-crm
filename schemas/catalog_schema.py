from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[UUID] = None  # for tree requests; not stored on Category directly here


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    parent_id: Optional[UUID] = None


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    stock: int = 0
    image_url: Optional[str] = None
    category_id: Optional[UUID] = None
    sub_category_id: Optional[UUID] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    stock: Optional[int] = None
    image_url: Optional[str] = None
    category_id: Optional[UUID] = None
    sub_category_id: Optional[UUID] = None


class ProductOut(ProductBase):
    id: UUID

    class Config:
        from_attributes = True


class CategoryOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    image_url: Optional[str] = None
    subcategories: List["CategoryOut"] = []

    class Config:
        from_attributes = True


CategoryOut.model_rebuild()


