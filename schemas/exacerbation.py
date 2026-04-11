from pydantic import BaseModel, Field
from typing import Optional
from datetime import date


class ExacerbationCreate(BaseModel):
    event_date: Optional[date] = None
    severity: int = Field(1, ge=1, le=3)
    triggered_by: Optional[str] = None


class ExacerbationResponse(BaseModel):
    id: int
    event_date: date
    severity: int
    triggered_by: Optional[str] = None

    class Config:
        from_attributes = True