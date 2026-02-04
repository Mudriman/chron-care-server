from pydantic import BaseModel
from datetime import date
from typing import Dict, Any, List


class RiskResponse(BaseModel):
    id: int
    risk_date: date
    risk_value: float
    risk_level: str
    model_version: str
    confidence: float
    factors: Dict[str, Any]
    recommendations: List[str]

    class Config:
        from_attributes = True