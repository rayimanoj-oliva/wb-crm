from datetime import datetime

from pydantic import BaseModel


class FileResponse(BaseModel):
    id: str
    name: str
    mimetype: str
    created_at: datetime

    class Config:
        from_attributes = True