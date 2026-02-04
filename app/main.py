# -*- coding: utf-8 -*-

from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter
from sqlmodel import SQLModel
from app.db.session import engine
from app.api import auth, patient, admin

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

app.include_router(auth.router, prefix="/auth")
app.include_router(patient.router, prefix="/patient")
app.include_router(admin.router, prefix="/admin")

@app.get("/")
def read_root():
    return {"message": "ChronCare API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}