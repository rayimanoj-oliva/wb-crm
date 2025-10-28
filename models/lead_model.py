"""
Lead Model for tracking Zoho leads locally
"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from models.models import Base
import uuid


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
    lead_source = Column(String(100), nullable=True)
    lead_status = Column(String(50), nullable=True)
    company = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    
    # WhatsApp information
    wa_id = Column(String, nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), nullable=True)
    
    # Appointment details stored as JSON
    appointment_details = Column(JSONB, nullable=True)
    
    # Treatment/Concern information
    treatment_name = Column(String(255), nullable=True)
    zoho_mapped_concern = Column(String(255), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Lead(zoho_lead_id='{self.zoho_lead_id}', name='{self.first_name} {self.last_name}')>"

