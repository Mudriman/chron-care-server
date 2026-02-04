from pydantic import BaseModel, Field
from datetime import date
from typing import Optional


class SymptomCreate(BaseModel):
    symptom_date: Optional[date] = None
    cough: int = Field(ge=0, le=3)
    breathlessness: int = Field(ge=0, le=3)
    night_symptoms: bool = False


class SymptomResponse(BaseModel):
    id: int
    symptom_date: date
    cough: int
    breathlessness: int
    night_symptoms: bool

    class Config:
        from_attributes = True
