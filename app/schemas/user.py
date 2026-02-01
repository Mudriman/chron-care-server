# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional


# Модели для запросов (DTO)
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Модели для ответов
class UserResponse(BaseModel):
    id: int
    email: str
    role: str  # Добавляем роль
    is_active: bool  # Добавляем статус

    class Config:
        from_attributes = True  # Ранее илиm_mode = True в Pydantic v1


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str