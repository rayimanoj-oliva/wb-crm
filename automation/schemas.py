from pydantic import BaseModel, Field
from typing import List, Optional, Any
from uuid import UUID

# Reply Material
class ReplyMaterialBase(BaseModel):
    type: str
    title: str
    content: Any
    preview: Optional[str] = None

class ReplyMaterialCreate(ReplyMaterialBase):
    pass

class ReplyMaterialUpdate(BaseModel):
    type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[Any] = None
    preview: Optional[str] = None

class ReplyMaterialOut(ReplyMaterialBase):
    id: UUID
    class Config:
        from_attributes = True

# Default Automation Rule
class DefaultAutomationRuleBase(BaseModel):
    rule_key: str
    is_enabled: bool
    material_id: UUID
    input_value: Optional[str] = None

class DefaultAutomationRuleCreate(DefaultAutomationRuleBase):
    pass

class DefaultAutomationRuleUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    material_id: Optional[UUID] = None
    input_value: Optional[str] = None

class DefaultAutomationRuleOut(DefaultAutomationRuleBase):
    id: UUID
    class Config:
        from_attributes = True

# Keyword Actions
class KeywordTermBase(BaseModel):
    value: str

class KeywordTermCreate(KeywordTermBase):
    pass

class KeywordTermOut(KeywordTermBase):
    id: UUID
    class Config:
        from_attributes = True

class KeywordReplyBase(BaseModel):
    material_id: UUID

class KeywordReplyCreate(KeywordReplyBase):
    pass

class KeywordReplyOut(KeywordReplyBase):
    id: UUID
    class Config:
        from_attributes = True

class KeywordBase(BaseModel):
    matching_type: str
    trigger_count: int = 0

class KeywordCreate(KeywordBase):
    terms: List[KeywordTermCreate]
    replies: List[KeywordReplyCreate]

class KeywordUpdate(BaseModel):
    matching_type: Optional[str] = None
    trigger_count: Optional[int] = None
    terms: Optional[List[KeywordTermCreate]] = None
    replies: Optional[List[KeywordReplyCreate]] = None

class KeywordOut(KeywordBase):
    id: UUID
    terms: List[KeywordTermOut]
    replies: List[KeywordReplyOut]
    class Config:
        from_attributes = True

# Routing Rule
class RoutingRuleBase(BaseModel):
    type: str
    material_id: UUID
    target_name: str

class RoutingRuleCreate(RoutingRuleBase):
    pass

class RoutingRuleUpdate(BaseModel):
    type: Optional[str] = None
    material_id: Optional[UUID] = None
    target_name: Optional[str] = None

class RoutingRuleOut(RoutingRuleBase):
    id: UUID
    class Config:
        from_attributes = True

# Working Hours
class Interval(BaseModel):
    from_time: str = Field(..., alias="from")
    to_time: str = Field(..., alias="to")

class WorkingHourBase(BaseModel):
    day: str
    open: bool
    intervals: List[Interval]

class WorkingHourCreate(WorkingHourBase):
    pass

class WorkingHourUpdate(BaseModel):
    open: Optional[bool] = None
    intervals: Optional[List[Interval]] = None

class WorkingHourOut(WorkingHourBase):
    id: UUID
    class Config:
        from_attributes = True

# Holiday Config
class HolidayConfigOut(BaseModel):
    holiday_mode: bool
    class Config:
        from_attributes = True

class HolidayConfigUpdate(BaseModel):
    holiday_mode: bool 