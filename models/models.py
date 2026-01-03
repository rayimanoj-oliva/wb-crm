"""
Models for Oliva Clinic CRM + Payments
CRM (WhatsApp, Campaigns, Customers)
E-commerce + Payment Integration (Razorpay + Shopify)
"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, JSON, Table,
    Enum as SAEnum, PrimaryKeyConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


# ------------------------------
# Enums
# ------------------------------

class CustomerStatusEnum(str, enum.Enum):
    pending = "pending"
    open = "open"
    resolved = "resolved"


user_role_enum = SAEnum(
    "SUPER_ADMIN", "ADMIN", "AGENT",
    name="user_role_enum",
    create_type=False  # Let Alembic handle enum creation
)


campaign_type_enum = ENUM(
    "text", "image", "document", "template", "interactive",
    name="campaign_type_enum",
    create_type=False
)


job_status_enum = SAEnum(
    "pending", "success", "failure",
    name="job_status_enum",
    create_type=False
)


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMethod(enum.Enum):
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    COD = "cod"


# ------------------------------
# Organization & Role
# ------------------------------

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False, index=True)  # SUPER_ADMIN, ORG_ADMIN, AGENT
    display_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    users = relationship("User", back_populates="role_obj")
    
    def __repr__(self):
        return f"<Role(name='{self.name}', display_name='{self.display_name}')>"


class Organization(Base):
    __tablename__ = "organizations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    code = Column(String(50), nullable=True, unique=True, index=True)  # Organization code (e.g., RH0007)
    slug = Column(String(255), nullable=True, unique=True, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships - only include models that have organization_id foreign key
    users = relationship("User", back_populates="organization")
    whatsapp_numbers = relationship("WhatsAppNumber", back_populates="organization")
    # Note: Other relationships (customers, campaigns, orders, leads, templates, zoho_mappings)
    # will be added later when organization_id columns are added to those tables
    
    def __repr__(self):
        return f"<Organization(name='{self.name}', slug='{self.slug}')>"


class WhatsAppNumber(Base):
    __tablename__ = "whatsapp_numbers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number_id = Column(String(100), nullable=False, unique=True, index=True)  # WhatsApp Business phone_number_id from Meta
    display_number = Column(String(50), nullable=True)  # Human-readable phone number (e.g., "+91 77299 92376")
    access_token = Column(String(500), nullable=True)  # WhatsApp Business API access token for this number
    webhook_path = Column(String(255), nullable=True)  # Webhook path/endpoint (e.g., "/webhook", "/webhook2")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="whatsapp_numbers")
    
    def __repr__(self):
        return f"<WhatsAppNumber(phone_number_id='{self.phone_number_id}', display_number='{self.display_number}', organization='{self.organization.name if self.organization else None}')>"


# ------------------------------
# User & Customer
# ------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    username = Column(String(100), nullable=False)
    password = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False)
    email = Column(String(100), nullable=False)
    role = Column(user_role_enum, nullable=True)  # Legacy field, kept for backward compatibility
    
    # New organization and role fields
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=True, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = relationship("Organization", back_populates="users")
    role_obj = relationship("Role", back_populates="users")
    customers = relationship("Customer", back_populates="user")
    
    # Composite unique constraints (username + organization_id, email + organization_id)
    __table_args__ = (
        Index('ix_users_username_organization', 'username', 'organization_id', unique=True),
        Index('ix_users_email_organization', 'email', 'organization_id', unique=True),
    )

class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wa_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String)
    # Primary and secondary phone numbers
    phone_1 = Column(String(20), nullable=True)
    phone_2 = Column(String(20), nullable=True)
    email = Column(String, nullable=True)

    # Optional default address shortcut
    default_address_id = Column(UUID(as_uuid=True), ForeignKey("customer_addresses.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_message_at = Column(DateTime, nullable=True)
    # Follow-up automation tracking
    last_interaction_time = Column(DateTime, nullable=True)
    last_message_type = Column(String(50), nullable=True)
    next_followup_time = Column(DateTime, nullable=True, index=True)  # Used by followup scheduler

    # Relations
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="customers")
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)

    orders = relationship("Order", back_populates="customer")
    campaigns = relationship("Campaign", secondary="campaign_customers", back_populates="customers")

    # Fix: specify foreign_keys for addresses
    addresses = relationship(
        "CustomerAddress",
        back_populates="customer",
        cascade="all, delete-orphan",
        foreign_keys="[CustomerAddress.customer_id]"  # explicitly tell SQLAlchemy which FK to use
    )

    # Default address relationship
    default_address = relationship(
        "CustomerAddress",
        foreign_keys=[default_address_id],
        post_update=True,
    )

    address_sessions = relationship(
        "AddressCollectionSession",
        back_populates="customer",
        cascade="all, delete-orphan"
    )

    customer_status = Column(
        SAEnum(CustomerStatusEnum, name="customer_status_enum", create_type=True),
        nullable=False,
        default="pending",
    )

    def __str__(self):
        return f"{self.wa_id} {self.name} {self.id}"


# ------------------------------
# Messaging / WhatsApp
# ------------------------------

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String)
    from_wa_id = Column(String)
    to_wa_id = Column(String)
    type = Column(String)  # "text", "image", "document", etc.
    body = Column(String)
    timestamp = Column(DateTime)

    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    center_id = Column(String)
    agent_id = Column(String, nullable=True)
    sender_type = Column(String)  # 'customer' or 'agent'

    media_id = Column(String, nullable=True)
    caption = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Relationship back to customer for convenient access
    customer = relationship("Customer", backref="messages")


class QuickReply(Base):
    __tablename__ = "quick_replies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(String(120), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("User")


class ReferrerTracking(Base):
    __tablename__ = "referrer_tracking"
    
    id = Column(Integer, primary_key=True, index=True)
    wa_id = Column(String, index=True)
    center_name = Column(String)  # e.g., "Oliva Clinics Banjara Hills"
    location = Column(String)     # e.g., "Hyderabad"
    created_at = Column(DateTime, default=func.now())
    
    # Appointment tracking fields
    appointment_date = Column(DateTime, nullable=True)  # Date of appointment
    appointment_time = Column(String, nullable=True)    # Time of appointment (e.g., "10:30 AM")
    treatment_type = Column(String, nullable=True)      # Type of treatment (e.g., "Hair Transplant", "PRP")
    is_appointment_booked = Column(Boolean, default=False)  # Flag to track if appointment was booked
    
    # Relationship to customer
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    customer = relationship("Customer", backref="referrer_tracking")


class WhatsAppToken(Base):
    __tablename__ = "whatsapp_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NumberFlowConfig(Base):
    """
    Stores enable/disable state for each WhatsApp business number flow.
    One row per dedicated business number.
    """

    __tablename__ = "number_flow_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number_id = Column(String, nullable=False, unique=True, index=True)
    display_number = Column(String, nullable=False)
    display_digits = Column(String(20), nullable=True, unique=True, index=True)
    flow_key = Column(String(100), nullable=False)
    flow_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Integer, default=0)
    is_enabled = Column(Boolean, default=True)
    auto_enable_from = Column(DateTime, nullable=True)
    auto_enable_to = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<NumberFlowConfig(flow_key={self.flow_key}, phone_number_id={self.phone_number_id}, enabled={self.is_enabled})>"


# ------------------------------
# Orders / Products
# ------------------------------

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), index=True)
    catalog_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    # Shipping address associated with the order
    shipping_address_id = Column(UUID(as_uuid=True), ForeignKey("customer_addresses.id"), nullable=True)

    # Order status and payment tracking
    status = Column(String(20), default="pending", index=True)  # pending, paid, shipped, delivered, cancelled
    payment_completed_at = Column(DateTime, nullable=True)
    
    # Track modification state
    modification_started_at = Column(DateTime, nullable=True)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    shipping_address = relationship("CustomerAddress")
    payments = relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    address_sessions = relationship("AddressCollectionSession", back_populates="order")


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), unique=True, index=True)
    price = Column(Float, nullable=False)
    description = Column(Text)
    image_url = Column(String(500), nullable=True)
    stock = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # New: Categorization
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True)
    sub_category_id = Column(UUID(as_uuid=True), ForeignKey("sub_categories.id", ondelete="SET NULL"), nullable=True)

    category = relationship("Category", back_populates="products")
    sub_category = relationship("SubCategory", back_populates="products")

    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.name}', sku='{self.sku}')>"


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"))
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)

    product_retailer_id = Column(String, nullable=True)  # for WhatsApp catalog products
    quantity = Column(Integer, nullable=False, default=1)
    price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    item_price = Column(Float, nullable=True)
    currency = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    # Track if this item was added during order modification
    is_modification_addition = Column(Boolean, default=False, nullable=False)
    modification_timestamp = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="items")
    product = relationship("Product")

    def __repr__(self):
        return f"<OrderItem(id={self.id}, order_id={self.order_id})>"


# ------------------------------
# Payments
# ------------------------------

class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True)  # Allow standalone payments
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="INR")
    razorpay_id = Column(String, nullable=True, index=True)
    razorpay_short_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="created", index=True)
    notification_sent = Column(Boolean, default=False)  # Track if payment link was sent to customer
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = relationship("Order", back_populates="payments")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id = Column(String(100), unique=True, nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)

    payment_method = Column(String(50), nullable=False)  # flexibility
    payment_gateway = Column(String(50), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="INR")
    status = Column(String(50), default="pending")
    gateway_transaction_id = Column(String(100))
    gateway_response = Column(JSONB)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<PaymentTransaction(id={self.id}, tx='{self.transaction_id}', status='{self.status}')>"


class OrderEvent(Base):
    __tablename__ = "order_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_data = Column(JSONB)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<OrderEvent(id={self.id}, order_id={self.order_id}, type='{self.event_type}')>"


class InventoryLog(Base):
    __tablename__ = "inventory_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    quantity_change = Column(Integer, nullable=False)
    reason = Column(String(100), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<InventoryLog(id={self.id}, product_id={self.product_id}, change={self.quantity_change})>"


# ------------------------------
# Flow Logs (Treatment + Lead Appointment)
# ------------------------------

class FlowLog(Base):
    __tablename__ = "flow_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Required columns for reporting
    wa_id = Column(String(64), nullable=True, index=True)
    name = Column(String(255), nullable=True)  # customer name if available
    flow_type = Column(String(50), nullable=False)  # "treatment" | "lead_appointment"
    step = Column(String(100), nullable=True)       # last step reached or "result"
    status_code = Column(Integer, nullable=True)    # API status/result code
    description = Column(Text, nullable=True)       # human-friendly description
    response_json = Column(Text, nullable=True)    # raw API response or payload

    # For sorting/filtering
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<FlowLog(id={self.id}, wa_id='{self.wa_id}', flow_type='{self.flow_type}', step='{self.step}', status_code={self.status_code})>"


# ------------------------------
# Address Management
# ------------------------------

class CustomerAddress(Base):
    __tablename__ = "customer_addresses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)

    # Address fields
    full_name = Column(String(100), nullable=False)
    house_street = Column(String(200), nullable=False)
    locality = Column(String(100), nullable=False)
    city = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False)
    pincode = Column(String(10), nullable=False)
    landmark = Column(String(100), nullable=True)
    phone = Column(String(15), nullable=False)

    # Location data
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Address metadata
    address_type = Column(String(20), default="home")  # home, office, other
    is_default = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Fix: specify foreign_keys for customer relationship
    customer = relationship(
        "Customer",
        back_populates="addresses",
        foreign_keys=[customer_id]
    )

    def __repr__(self):
        return f"<CustomerAddress(id={self.id}, customer_id={self.customer_id}, city='{self.city}')>"


class AddressCollectionSession(Base):
    __tablename__ = "address_collection_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True)
    
    # Session state
    status = Column(String(20), default="pending")  # pending, collecting, completed, cancelled
    collection_method = Column(String(20), nullable=True)  # location, manual, saved
    
    # Session data
    session_data = Column(JSONB, nullable=True)  # Store intermediate data
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    customer = relationship("Customer", back_populates="address_sessions")
    order = relationship("Order", back_populates="address_sessions")
    
    def __repr__(self):
        return f"<AddressCollectionSession(id={self.id}, customer_id={self.customer_id}, status='{self.status}')>"


# ------------------------------
# Catalog: Categories & Sub-Categories
# ------------------------------

class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), unique=True, nullable=False)
    slug = Column(String(140), unique=True, nullable=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sub_categories = relationship(
        "SubCategory",
        back_populates="category",
        cascade="all, delete-orphan"
    )
    products = relationship("Product", back_populates="category")

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"


class SubCategory(Base):
    __tablename__ = "sub_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(120), nullable=False)
    slug = Column(String(140), unique=True, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category = relationship("Category", back_populates="sub_categories")
    products = relationship("Product", back_populates="sub_category")

    def __repr__(self):
        return f"<SubCategory(id={self.id}, name='{self.name}', category_id={self.category_id})>"


# ------------------------------
# Campaigns / Jobs
# ------------------------------

class TemplateMessage(Base):
    __tablename__ = "template_messages"

    message_id = Column(String, nullable=False)
    template_id = Column(String, nullable=False)
    var_name = Column(String, nullable=False)
    var_val = Column(String, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("message_id", "template_id", "var_name", name="template_message_pk"),
    )


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    campaign_cost_type = Column(String, ForeignKey("costs.type"))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    content = Column(JSONB, nullable=True)
    type = Column(campaign_type_enum, nullable=False, index=True)

    last_job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    # Campaign status: idle, running, stopped
    status = Column(String(20), default="idle", index=True)

    jobs = relationship(
        "Job",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[Job.campaign_id]"
    )
    last_job = relationship("Job", foreign_keys=[last_job_id], post_update=True)
    cost = relationship("Cost", backref="campaigns")
    customers = relationship("Customer", secondary="campaign_customers", back_populates="campaigns")
    recipients = relationship(
        "CampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True
    )


campaign_customers = Table(
    "campaign_customers",
    Base.metadata,
    Column("campaign_id", UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True),
    Column("customer_id", UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), primary_key=True),
)

class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    name = Column(String(100), nullable=True)
    params = Column(JSON, nullable=True)  # flexible key/value for template params
    status = Column(String(20), default="PENDING", index=True)  # PENDING, SENT, FAILED
    created_at = Column(DateTime, default=datetime.utcnow)

    campaign = relationship("Campaign", back_populates="recipients")



class Template(Base):
    __tablename__ = "templates"

    template_name = Column(String, primary_key=True)
    template_body = Column(JSONB, nullable=False)
    template_vars = Column(JSONB, nullable=False)
    facebook_template_id = Column(String, nullable=True, index=True)  # Facebook's template ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Template(template_name='{self.template_name}', fb_id='{self.facebook_template_id}')>"


class File(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True, index=True)  # media_id from Meta
    name = Column(String, nullable=False)
    mimetype = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    last_attempted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    last_triggered_time = Column(DateTime, nullable=True)

    campaign = relationship("Campaign", back_populates="jobs", foreign_keys=[campaign_id])
    attempted_by_user = relationship("User", backref="attempted_jobs")


class JobStatus(Base):
    __tablename__ = "job_status"

    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    status = Column(job_status_enum, nullable=False, default="pending")

    __table_args__ = (
        PrimaryKeyConstraint("job_id", "customer_id", name="job_status_pk"),
    )

    job = relationship("Job", backref="statuses")
    customer = relationship("Customer")


class Cost(Base):
    __tablename__ = "costs"

    type = Column(String(50), primary_key=True)
    price = Column(Float, nullable=False)

    def __repr__(self):
        return f"<Cost(type='{self.type}', price={self.price})>"


class ZohoMapping(Base):
    __tablename__ = "zoho_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    treatment_name = Column(String(255), nullable=False, unique=True, index=True)
    zoho_name = Column(String(255), nullable=False, index=True)
    zoho_sub_concern = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<ZohoMapping(id={self.id}, treatment_name='{self.treatment_name}', zoho_name='{self.zoho_name}')>"


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    zoho_lead_id = Column(String, unique=True, nullable=False, index=True)

    # Lead information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=False, index=True)
    mobile = Column(String(20), nullable=True)

    # Lead details
    city = Column(String(100), nullable=True)
    location = Column(String(100), nullable=True)
    lead_source = Column(String(100), nullable=True)
    company = Column(String(100), nullable=True)

    # WhatsApp information
    wa_id = Column(String, nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=True)

    # Appointment details stored as JSON
    appointment_details = Column(JSONB, nullable=True)

    # Treatment/Concern information
    treatment_name = Column(String(255), nullable=True)
    zoho_mapped_concern = Column(String(255), nullable=True)
    primary_concern = Column(String(255), nullable=True)
    sub_source = Column(String(50), nullable=True, default="Chats")

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Lead(zoho_lead_id='{self.zoho_lead_id}', name='{self.first_name} {self.last_name}')>"


# ------------------------------
# Campaign Logs (Detailed logging for bulk campaigns)
# ------------------------------

class CampaignLog(Base):
    """Detailed logging for campaign message sending"""
    __tablename__ = "campaign_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Campaign/Job reference
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=True, index=True)

    # Target information
    target_type = Column(String(20), nullable=False)  # "recipient" or "customer"
    target_id = Column(UUID(as_uuid=True), nullable=True)
    phone_number = Column(String(20), nullable=True, index=True)

    # Status and result
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, success, failure, queued
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # WhatsApp API details
    whatsapp_message_id = Column(String(100), nullable=True)
    http_status_code = Column(Integer, nullable=True)

    # Request/Response data for debugging
    request_payload = Column(JSONB, nullable=True)
    response_data = Column(JSONB, nullable=True)

    # Timing
    processing_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    processed_at = Column(DateTime, nullable=True)

    # Retry tracking
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime, nullable=True)

    # Composite index for fast upsert lookups (job_id + target_id)
    __table_args__ = (
        Index('ix_campaign_logs_job_target', 'job_id', 'target_id'),
    )

    # Relationships (passive_deletes=True to let DB handle CASCADE)
    campaign = relationship("Campaign", backref=backref("logs", passive_deletes=True))
    job = relationship("Job", backref=backref("logs", passive_deletes=True))

    def __repr__(self):
        return f"<CampaignLog(id={self.id}, campaign_id={self.campaign_id}, phone={self.phone_number}, status='{self.status}')>"


class WhatsAppAPILog(Base):
    """Debug log for all WhatsApp API requests and responses"""
    __tablename__ = "whatsapp_api_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    job_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    phone_number = Column(String(20), nullable=True, index=True)

    # Request details
    request_url = Column(String(500), nullable=True)
    request_payload = Column(JSONB, nullable=True)
    request_headers = Column(JSONB, nullable=True)

    # Response details
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(JSONB, nullable=True)
    response_headers = Column(JSONB, nullable=True)

    # Meta message details
    whatsapp_message_id = Column(String(100), nullable=True)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timing
    request_time = Column(DateTime, nullable=True)
    response_time = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<WhatsAppAPILog(id={self.id}, phone={self.phone_number}, status={self.response_status_code})>"

class ZohoPayloadLog(Base):
    """Log table for Zoho API payloads and responses"""
    __tablename__ = 'zoho_payload_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    wa_id = Column(String(50), index=True)
    lead_id = Column(String(100))
    zoho_lead_id = Column(String(100))
    payload = Column(JSONB)
    response = Column(JSONB)
    status = Column(String(50))  # 'success', 'error', 'duplicate'
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self):
        return f"<ZohoPayloadLog(id={self.id}, wa_id={self.wa_id}, status={self.status})>"
