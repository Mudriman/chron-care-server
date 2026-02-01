# app/api/patient.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select
from typing import List
import logging

from app.db.session import get_session
from app.db.models import User
from app.core.dependencies import get_current_patient

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/meds")
def create_medication(
    current_user: User = Depends(get_current_patient)
):
    return {"message": "Medication created", "user_id": current_user.id}

@router.get("/meds")
def get_medications(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_patient)
):
    return {"message": f"Medications for user {current_user.id}", "skip": skip, "limit": limit}

@router.delete("/meds/{medication_id}")
def delete_medication(
    medication_id: int,
    current_user: User = Depends(get_current_patient)
):
    return {"message": f"Medication {medication_id} deleted", "user_id": current_user.id}

@router.post("/symptoms")
def create_symptom(
    current_user: User = Depends(get_current_patient)
):
    return {"message": "Symptom reported", "user_id": current_user.id}

@router.get("/symptoms")
def get_symptoms(
    current_user: User = Depends(get_current_patient)
):
    return {"message": f"Symptoms for user {current_user.id}"}

@router.get("/risk/today")
def get_today_risk(
    current_user: User = Depends(get_current_patient)
):
    return {
        "message": "Today's risk",
        "user_id": current_user.id,
        "risk_level": 0.3
    }

@router.post("/risk/recalculate")
def recalculate_risk(
    current_user: User = Depends(get_current_patient)
):
    return {"message": "Risk recalculated", "user_id": current_user.id}

@router.get("/reports/weekly")
def get_weekly_report(
    current_user: User = Depends(get_current_patient)
):
    return {"message": "Weekly report", "user_id": current_user.id}