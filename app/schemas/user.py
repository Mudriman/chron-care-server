# app/schemas/user.py
from pydantic import BaseModel, EmailStr
from typing import Optional


# Модели для запросов (DTO)
class UserRegister(BaseModel):
    email: EmailStr  # Используем EmailStr для валидации email
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


# Модели для ответов
class UserResponse(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True  # Ранее илиm_mode = True в Pydantic v1


class TokenResponse(BaseModel):
    access_token: str
    token_type: str