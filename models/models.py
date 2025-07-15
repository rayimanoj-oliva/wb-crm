from sqlalchemy import Enum

from sqlalchemy.dialects.postgresql import JSONB, ENUM
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
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

Base = declarative_base()

user_role_enum = Enum(
    "ADMIN", "AGENT",
    name="user_role_enum",
    create_type=False  # Let Alembic handle enum creation
)
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
    orders = relationship("Order", back_populates="customer")
    address = Column(String, nullable=True)
    campaigns = relationship("Campaign", secondary="campaign_customers", back_populates="customers")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime, nullable=True)
    # foreign key
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationship to User
    user = relationship("User", back_populates="customers")
    def __str__(self):
        return f"{self.wa_id} {self.name} {self.id}"



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

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    campaign_cost_type = Column(String, ForeignKey("costs.type"))
    content = Column(JSONB, nullable=True)
    type = Column(campaign_type_enum, nullable=False)

    # 🆕 Last job reference
    last_job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)

    # ✅ FIX HERE: Specify which FK column this relationship uses
    jobs = relationship(
        "Job",
        back_populates="campaign",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[Job.campaign_id]"  # 🛠 important!
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
    last_attempted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    last_triggered_time = Column(DateTime, nullable=True)

    # ✅ Specify foreign key explicitly to avoid ambiguity
    campaign = relationship("Campaign", back_populates="jobs", foreign_keys=[campaign_id])

    attempted_by_user = relationship("User", backref="attempted_jobs")

jobs = relationship(
    "Job",
    back_populates="campaign",
    cascade="all, delete-orphan",
    passive_deletes=True,
    foreign_keys=[Job.campaign_id]  # ✅ correct usage (no quotes)
)


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


class Cost(Base):
    __tablename__ = "costs"

    type = Column(String(50), primary_key=True)  # e.g., "SMS", "WhatsApp", etc.
    price = Column(Float, nullable=False)        # e.g., 0.25, 1.50

    def __repr__(self):
        return f"<Cost(type='{self.type}', price={self.price})>"


#comment