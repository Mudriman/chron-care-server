# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # 👈 1. ИМПОРТ
from sqlmodel import SQLModel
from app.db.session import engine
from app.api import auth, patient, admin, user

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")
    SQLModel.metadata.create_all(engine)
    yield
    print("Shutting down...")

app = FastAPI(
    title="ChronCare API",
    lifespan=lifespan
)

# 👇 2. ДОБАВЬТЕ ЭТО (всего 8 строк)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В разработке разрешаем все источники
    allow_methods=["*"],  # Разрешаем все методы (включая OPTIONS)
    allow_headers=["*"],  # Разрешаем все заголовки
    allow_credentials=True,
)

# 👇 3. ЯВНАЯ ОБРАБОТКА OPTIONS (ещё 3 строки)
@app.options("/{rest_of_path:path}")
async def options_handler():
    return {}

# Подключаем роутеры
app.include_router(auth.router, prefix="/auth")
app.include_router(patient.router, prefix="/patient")
app.include_router(admin.router, prefix="/admin")
app.include_router(user.router, prefix="/user")

@app.get("/")
def read_root():
    return {"message": "ChronCare API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}