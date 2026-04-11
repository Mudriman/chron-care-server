# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Any, Optional, List


# Модели для запросов (DTO)
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")


class UserLogin(BaseModel):
    email: EmailStr
    password: str

class OnboardingUpdate(BaseModel):
    asthma_type: Optional[str] = Field(None)
    baseline_severity: Optional[str] = Field(None)
    known_triggers: Optional[List[str]] = None
    years_since_diagnosis: Optional[int] = None
    smoker: Optional[bool] = None

# Модели для ответов
class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    is_active: bool
    avatar_id: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str

class UserUpdate(BaseModel):
    avatar_id: Optional[str] = Field(None, max_length=50, description="Avatar ID")