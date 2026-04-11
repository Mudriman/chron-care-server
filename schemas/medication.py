from pydantic import BaseModel, Field
from datetime import date
from typing import Optional


class MedicationCreate(BaseModel):
    name: str
    dosage: str
    frequency_per_day: int = Field(ge=1, le=6)
    end_date: Optional[date] = None
    notes: Optional[str] = Field(None, max_length=500)
    notifications_enabled: bool = True


class MedicationResponse(BaseModel):
    id: int
    name: str
    dosage: str
    frequency_per_day: int
    start_date: date
    end_date: Optional[date]
    is_active: bool
    notes: Optional[str]
    notifications_enabled: bool

    class Config:
        from_attributes = True


class MedicationUpdate(BaseModel):
    name: Optional[str] = None
    dosage: Optional[str] = None
    frequency_per_day: Optional[int] = Field(None, ge=1, le=6)
    end_date: Optional[date] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = Field(None, max_length=500)
    notifications_enabled: Optional[bool] = None

    class Config:
        extra = "forbid"