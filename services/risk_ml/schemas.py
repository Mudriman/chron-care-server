from pydantic import BaseModel
from typing import Dict, Any


class RiskMLResponse(BaseModel):
    risk_value: float
    risk_level: str
    features: Dict[str, Any]