from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional


class IntakeCreate(BaseModel):
    medication_id: int
    intake_date: date


class IntakeResponse(BaseModel):
    id: int
    medication_id: int
    intake_date: date
    taken: bool
    taken_at: Optional[datetime]

    class Config:
        from_attributes = True

