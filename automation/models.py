from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base
import uuid
# from models.models import Base
from sqlalchemy.dialects.postgresql import ENUM
Base = declarative_base()
reply_material_type_enum = ENUM(
    "text", "image", "template", "document", "video", "audio", name="reply_material_type_enum", create_type=True
)

keyword_matching_enum = ENUM(
    "exact", "fuzzy", "contains", name="keyword_matching_enum", create_type=True
)

routing_type_enum = ENUM("user", "team", name="routing_type_enum", create_type=True)
class ReplyMaterial(Base):
    __tablename__ = "reply_materials"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(reply_material_type_enum, nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(JSONB, nullable=False)
    preview = Column(String(255), nullable=True)

class DefaultAutomationRule(Base):
    __tablename__ = "default_automation_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_key = Column(String(100), nullable=False, unique=True)
    is_enabled = Column(Integer, default=1)
    material_id = Column(UUID(as_uuid=True), ForeignKey("reply_materials.id"), nullable=False)
    input_value = Column(String(255), nullable=True)
    material = relationship("ReplyMaterial")

class Keyword(Base):
    __tablename__ = "keywords"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    matching_type = Column(keyword_matching_enum, nullable=False)
    trigger_count = Column(Integer, default=0)
    terms = relationship("KeywordTerm", back_populates="keyword", cascade="all, delete-orphan")
    replies = relationship("KeywordReply", back_populates="keyword", cascade="all, delete-orphan")

class KeywordTerm(Base):
    __tablename__ = "keyword_terms"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keyword_id = Column(UUID(as_uuid=True), ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False)
    value = Column(String(255), nullable=False)
    keyword = relationship("Keyword", back_populates="terms")

class KeywordReply(Base):
    __tablename__ = "keyword_replies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keyword_id = Column(UUID(as_uuid=True), ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False)
    material_id = Column(UUID(as_uuid=True), ForeignKey("reply_materials.id", ondelete="CASCADE"), nullable=False)
    keyword = relationship("Keyword", back_populates="replies")
    material = relationship("ReplyMaterial")

class RoutingRule(Base):
    __tablename__ = "routing_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column(routing_type_enum, nullable=False)
    material_id = Column(UUID(as_uuid=True), ForeignKey("reply_materials.id"), nullable=False)
    target_name = Column(String(255), nullable=False)
    material = relationship("ReplyMaterial")

class WorkingHour(Base):
    __tablename__ = "working_hours"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day = Column(String(10), nullable=False)
    open = Column(Integer, default=1)
    intervals = Column(JSONB, nullable=False)

class HolidayConfig(Base):
    __tablename__ = "holiday_config"
    id = Column(Integer, primary_key=True, default=1)
    holiday_mode = Column(Integer, default=0) 