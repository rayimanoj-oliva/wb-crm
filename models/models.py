from sqlalchemy import Enum
from sqlalchemy.sql import func
import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Float, PrimaryKeyConstraint, Table,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone_number = Column(String(20), nullable=False)
    email = Column(String(100), unique=True, nullable=False)

class Customer(Base):
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wa_id = Column(String, unique=True, nullable=False)
    name = Column(String)

    orders = relationship("Order", back_populates="customer")
    campaigns = relationship("Campaign", secondary="campaign_customers", back_populates="customers")

    def __str__(self):
        return f"{self.wa_id} {self.name} {self.id}"


from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(String)
    from_wa_id = Column(String)
    to_wa_id = Column(String)
    type = Column(String)  # "text", "image", "document", etc.
    body = Column(String)
    timestamp = Column(DateTime)

    customer_id = Column(PG_UUID(as_uuid=True), ForeignKey("customers.id"))

    # Optional fields for media
    media_id = Column(String, nullable=True)
    caption = Column(String, nullable=True)
    filename = Column(String, nullable=True)
    mime_type = Column(String, nullable=True)


class WhatsAppToken(Base):
    __tablename__ = "whatsapp_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    catalog_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    customer = relationship("Customer", back_populates="orders")

class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"))
    product_retailer_id = Column(String)
    quantity = Column(Integer)
    item_price = Column(Float)
    currency = Column(String)

    order = relationship("Order", back_populates="items")

class TemplateMessage(Base):
    __tablename__ = "template_messages"

    message_id = Column(String, nullable=False)      # e.g., WhatsApp message ID
    template_id = Column(String, nullable=False)     # e.g., "nps_temp1"
    var_name = Column(String, nullable=False)        # e.g., "name", "link"
    var_val = Column(String, nullable=False)         # e.g., "Manoj Rayi"

    __table_args__ = (
        PrimaryKeyConstraint("message_id", "template_id", "var_name", name="template_message_pk"),
    )

campaign_type_enum = ENUM(
    "text", "image", "document", "template", "interactive",
    name="campaign_type_enum",
    create_type=False  # Alembic will manage this
)

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Many-to-many relationship with customers
    customers = relationship("Customer", secondary="campaign_customers", back_populates="campaigns")
    content = Column(JSONB, nullable=True)
    type = Column(campaign_type_enum, nullable=False)
    jobs = relationship(
        "Job",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

campaign_customers = Table(
    "campaign_customers",
    Base.metadata,
    Column("campaign_id", UUID(as_uuid=True), ForeignKey("campaigns.id"), primary_key=True),
    Column("customer_id", UUID(as_uuid=True), ForeignKey("customers.id"), primary_key=True),
)


class Template(Base):
    __tablename__ = 'templates'

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

    campaign = relationship("Campaign", back_populates="jobs")




job_status_enum = Enum("pending", "success", "failure", name="job_status_enum", create_type=False)

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

