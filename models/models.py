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
    Enum as SAEnum, PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.orm import relationship
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
    "ADMIN", "AGENT",
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
# User & Customer
# ------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    role = Column(user_role_enum, nullable=False, default="AGENT")

    customers = relationship("Customer", back_populates="user")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wa_id = Column(String, unique=True, nullable=False)
    name = Column(String)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)

    # relations
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    user = relationship("User", back_populates="customers")

    orders = relationship("Order", back_populates="customer")
    campaigns = relationship("Campaign", secondary="campaign_customers", back_populates="customers")

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


class WhatsAppToken(Base):
    __tablename__ = "whatsapp_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ------------------------------
# Orders / Products
# ------------------------------

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    catalog_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), unique=True, index=True)
    price = Column(Float, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=True)  # Allow standalone payments
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="INR")
    razorpay_id = Column(String, nullable=True)
    razorpay_short_url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="created")
    notification_sent = Column(Boolean, default=False)  # Track if payment link was sent to customer
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = relationship("Order")


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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    campaign_cost_type = Column(String, ForeignKey("costs.type"))
    content = Column(JSONB, nullable=True)
    type = Column(campaign_type_enum, nullable=False)

    last_job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)

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


campaign_customers = Table(
    "campaign_customers",
    Base.metadata,
    Column("campaign_id", UUID(as_uuid=True), ForeignKey("campaigns.id"), primary_key=True),
    Column("customer_id", UUID(as_uuid=True), ForeignKey("customers.id"), primary_key=True),
)


class Template(Base):
    __tablename__ = "templates"

    template_name = Column(String, primary_key=True)
    template_body = Column(JSONB, nullable=False)
    template_vars = Column(JSONB, nullable=False)

    def __repr__(self):
        return f"<Template(template_name='{self.template_name}')>"


class File(Base):
    __tablename__ = "files"

    id = Column(String, primary_key=True, index=True)  # media_id from Meta
    name = Column(String, nullable=False)
    mimetype = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
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
