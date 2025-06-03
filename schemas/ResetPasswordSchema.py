from pydantic import BaseModel, Field
from typing import Annotated

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: Annotated[str, Field(min_length=8)]
