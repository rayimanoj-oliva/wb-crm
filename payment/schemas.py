"""
Payment Schemas - Data models and validation for payment operations
Defines request/response models for payment processing
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class PaymentStatus(str, Enum):
    """Payment status enumeration"""
    CREATED = "created"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PENDING = "pending"


class PaymentMethod(str, Enum):
    """Payment method enumeration"""
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    EMI = "emi"


class CustomerInfo(BaseModel):
    """Customer information for payment"""
    name: Optional[str] = Field(None, description="Customer name")
    email: Optional[str] = Field(None, description="Customer email")
    phone: Optional[str] = Field(None, description="Customer phone number")
    wa_id: Optional[str] = Field(None, description="WhatsApp ID")


class PaymentCreate(BaseModel):
    """Payment creation request model"""
    order_id: Optional[str] = Field(None, description="Associated order ID")
    amount: float = Field(..., gt=0, description="Payment amount in rupees")
    currency: str = Field("INR", description="Currency code")
    payment_method: Optional[PaymentMethod] = Field(PaymentMethod.UPI, description="Preferred payment method")
    
    # Customer information (flat fields)
    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_email: Optional[str] = Field(None, description="Customer email")
    customer_phone: Optional[str] = Field(None, description="Customer phone")
    
    # Customer information (nested object)
    customer: Optional[CustomerInfo] = Field(None, description="Customer information")
    
    # Additional metadata
    description: Optional[str] = Field(None, description="Payment description")
    notes: Optional[Dict[str, Any]] = Field(None, description="Additional notes")
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError('Amount must be greater than 0')
        if v > 1000000:  # 10 lakh rupees limit
            raise ValueError('Amount exceeds maximum limit')
        return v
    
    @validator('currency')
    def validate_currency(cls, v):
        allowed_currencies = ['INR', 'USD', 'EUR', 'GBP']
        if v.upper() not in allowed_currencies:
            raise ValueError(f'Currency must be one of: {allowed_currencies}')
        return v.upper()


class PaymentResponse(BaseModel):
    """Payment creation response model"""
    payment_id: str = Field(..., description="Internal payment ID")
    razorpay_id: str = Field(..., description="Razorpay payment ID")
    payment_url: str = Field(..., description="Payment link URL")
    status: PaymentStatus = Field(..., description="Payment status")
    amount: float = Field(..., description="Payment amount")
    currency: str = Field(..., description="Currency")
    order_id: Optional[str] = Field(None, description="Associated order ID")
    created_at: datetime = Field(..., description="Payment creation timestamp")
    expires_at: Optional[datetime] = Field(None, description="Payment link expiration")
    notification_sent: bool = Field(False, description="Whether notification was sent")


class PaymentUpdate(BaseModel):
    """Payment update request model"""
    status: Optional[PaymentStatus] = Field(None, description="New payment status")
    notes: Optional[Dict[str, Any]] = Field(None, description="Additional notes")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class PaymentWebhook(BaseModel):
    """Razorpay webhook payload model"""
    event: str = Field(..., description="Webhook event type")
    created_at: int = Field(..., description="Event creation timestamp")
    payload: Dict[str, Any] = Field(..., description="Event payload data")
    
    class Config:
        extra = "allow"  # Allow additional fields from Razorpay


class PaymentLinkRequest(BaseModel):
    """Payment link creation request"""
    order_id: str = Field(..., description="Order ID")
    customer_wa_id: str = Field(..., description="Customer WhatsApp ID")
    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_email: Optional[str] = Field(None, description="Customer email")
    customer_phone: Optional[str] = Field(None, description="Customer phone")


class PaymentLinkResponse(BaseModel):
    """Payment link creation response"""
    success: bool = Field(..., description="Whether payment link was created successfully")
    payment_id: Optional[str] = Field(None, description="Payment ID")
    payment_url: Optional[str] = Field(None, description="Payment URL")
    order_total: Optional[float] = Field(None, description="Order total amount")
    currency: Optional[str] = Field(None, description="Currency")
    error: Optional[str] = Field(None, description="Error message if failed")
    error_type: Optional[str] = Field(None, description="Error type")


class PaymentDiagnostics(BaseModel):
    """Payment system diagnostics model"""
    razorpay_config: Dict[str, Any] = Field(..., description="Razorpay configuration status")
    environment: Dict[str, Any] = Field(..., description="Environment variables status")
    api_test: Dict[str, Any] = Field(..., description="API connectivity test results")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Diagnostics timestamp")


class OrderSummary(BaseModel):
    """Order summary for payment display"""
    order_id: str = Field(..., description="Order ID")
    total_amount: float = Field(..., description="Total amount")
    currency: str = Field(..., description="Currency")
    items_count: int = Field(..., description="Number of items")
    formatted_total: str = Field(..., description="Formatted total amount")
    items: list = Field(..., description="List of order items")
    subtotal: Optional[float] = Field(None, description="Subtotal before discounts")
    discount_amount: Optional[float] = Field(None, description="Discount amount")


class CartCalculation(BaseModel):
    """Cart calculation result"""
    order_id: str = Field(..., description="Order ID")
    subtotal: float = Field(..., description="Subtotal amount")
    discount_amount: float = Field(0.0, description="Discount amount")
    total_amount: float = Field(..., description="Final total amount")
    currency: str = Field("INR", description="Currency")
    items_count: int = Field(..., description="Number of items")
    items_summary: list = Field(..., description="Items summary")
