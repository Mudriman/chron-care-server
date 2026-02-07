# -*- coding: utf-8 -*-

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlmodel import Session, select, and_
from typing import List, Optional
import logging
from datetime import timedelta, datetime, timezone

from app.db.session import get_session
from app.db.models import User, Medication, SymptomEntry, MedicationIntake, get_current_utc_date, RiskScore, DailyContext
from app.core.dependencies import get_current_patient
from app.schemas.medication import MedicationCreate, MedicationResponse
from app.schemas.symptom import SymptomCreate, SymptomResponse
from app.schemas.intake import IntakeCreate, IntakeResponse
from app.services.risk.risk_service import RiskService
from app.schemas.risk import RiskResponse
from app.services.weather.weather_service import WeatherService

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/meds",
    response_model=MedicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add new medication"
)
def create_medication(
        medication_data: MedicationCreate,
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Add new medication for current patient"""
    logger.info(f"Creating medication for user {current_user.id}")

    existing_med = session.exec(
        select(Medication).where(
            and_(
                Medication.user_id == current_user.id,
                Medication.name == medication_data.name,
                Medication.is_active == True
            )
        )
    ).first()

    if existing_med:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Active medication '{medication_data.name}' already exists"
        )

    # Создаем новое лекарство
    new_medication = Medication(
        **medication_data.dict(),
        user_id=current_user.id,
        start_date=get_current_utc_date()
    )

    try:
        session.add(new_medication)
        session.commit()
        session.refresh(new_medication)

        logger.info(f"Medication created: {new_medication.id} ({new_medication.name})")
        return new_medication

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating medication: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create medication"
        )


@router.get(
    "/meds",
    response_model=List[MedicationResponse],
    summary="Get all medications"
)
def get_medications(
        active_only: bool = Query(True, description="Show only active medications"),
        skip: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=1000),
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Get all medications for current patient"""
    query = select(Medication).where(Medication.user_id == current_user.id)

    if active_only:
        query = query.where(Medication.is_active == True)

    query = query.offset(skip).limit(limit).order_by(Medication.start_date.desc())

    medications = session.exec(query).all()

    logger.info(f"Retrieved {len(medications)} medications for user {current_user.id}")
    return medications


@router.delete(
    "/meds/{medication_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete (deactivate) medication"
)
def delete_medication(
        medication_id: int,
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Deactivate medication by ID"""
    logger.info(f"Deactivating medication {medication_id} for user {current_user.id}")

    medication = session.get(Medication, medication_id)

    if not medication:
        logger.warning(f"Medication {medication_id} not found for user {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found"
        )

    if medication.user_id != current_user.id:
        logger.warning(
            f"User {current_user.id} attempted to deactivate "
            f"medication {medication_id} belonging to user {medication.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot deactivate medication of another user"
        )

    if not medication.is_active:
        logger.info(f"Medication {medication_id} is already inactive")
        # Можно вернуть 200, т.к. результат тот же - лекарство неактивно
        return

    # Деактивируем лекарство
    medication.is_active = False
    medication.end_date = get_current_utc_date()

    try:
        session.add(medication)
        session.commit()
        logger.info(f"Medication {medication_id} deactivated successfully")

    except Exception as e:
        session.rollback()
        logger.error(f"Error deactivating medication {medication_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate medication"
        )


@router.post(
    "/symptoms",
    response_model=SymptomResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Report daily symptoms"
)
def create_symptom(
        symptom_data: SymptomCreate,
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Report daily symptoms for current patient"""
    # Используем сегодняшнюю дату, если не указана
    symptom_date = symptom_data.symptom_date or get_current_utc_date()

    logger.info(f"Creating symptom entry for user {current_user.id}, date: {symptom_date}")

    # Проверяем, не существует ли уже запись за эту дату
    existing_entry = session.exec(
        select(SymptomEntry).where(
            SymptomEntry.user_id == current_user.id,
            SymptomEntry.symptom_date == symptom_date
        )
    ).first()

    if existing_entry:
        # Обновляем существующую запись
        existing_entry.cough = symptom_data.cough
        existing_entry.breathlessness = symptom_data.breathlessness
        existing_entry.night_symptoms = symptom_data.night_symptoms

        session.add(existing_entry)
        session.commit()
        session.refresh(existing_entry)

        logger.info(f"Symptom entry updated: {existing_entry.id}")
        return existing_entry

    # Создаем новую запись
    new_symptom = SymptomEntry(
        cough=symptom_data.cough,
        breathlessness=symptom_data.breathlessness,
        night_symptoms=symptom_data.night_symptoms,
        symptom_date=symptom_date,
        user_id=current_user.id
    )

    try:
        session.add(new_symptom)
        session.commit()
        session.refresh(new_symptom)

        logger.info(f"Symptom entry created: {new_symptom.id}")
        return new_symptom

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating symptom entry: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create symptom entry"
        )



@router.get(
    "/symptoms",
    response_model=List[SymptomResponse],
    summary="Get symptom history"
)
def get_symptoms(
        days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Get symptom history for current patient"""
    start_date = datetime.now(timezone.utc).date() - timedelta(days=days)

    symptoms = session.exec(
        select(SymptomEntry).where(
            and_(
                SymptomEntry.user_id == current_user.id,
                SymptomEntry.symptom_date >= start_date
            )
        ).order_by(SymptomEntry.symptom_date.desc())
    ).all()

    logger.info(f"Retrieved {len(symptoms)} symptom entries for user {current_user.id}")
    return symptoms


@router.post(
    "/intakes",
    response_model=IntakeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mark medication intake"
)
def create_intake(
        intake_data: IntakeCreate,
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Mark medication intake for today"""
    logger.info(f"Marking intake for medication {intake_data.medication_id} by user {current_user.id}")

    intake_date = get_current_utc_date()
    logger.info(f"Using intake date (UTC): {intake_date}")

    # Проверяем лекарство
    medication = session.get(Medication, intake_data.medication_id)

    if not medication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found"
        )

    if medication.user_id != current_user.id:
        logger.warning(
            f"User {current_user.id} attempted to mark intake "
            f"for medication belonging to user {medication.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot mark intake for medication of another user"
        )

    if not medication.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot mark intake for inactive medication"
        )

    # === ИСПРАВЛЕНИЕ 2: Используем правильную дату для поиска ===
    existing_intake = session.exec(
        select(MedicationIntake).where(
            and_(
                MedicationIntake.user_id == current_user.id,
                MedicationIntake.medication_id == intake_data.medication_id,
                MedicationIntake.intake_date == intake_date  # <-- используем intake_date, не intake_data.intake_date
            )
        )
    ).first()

    if existing_intake:
        # Обновляем существующую отметку
        existing_intake.taken = True
        existing_intake.taken_at = datetime.now(timezone.utc)

        session.add(existing_intake)
        session.commit()
        session.refresh(existing_intake)

        logger.info(f"Intake updated: {existing_intake.id}")
        return existing_intake

    # === ИСПРАВЛЕНИЕ 3: Явно указываем intake_date при создании ===
    new_intake = MedicationIntake(
        user_id=current_user.id,
        medication_id=intake_data.medication_id,
        intake_date=intake_date,  # <-- ЯВНО указываем
        taken=True,
        taken_at=datetime.now(timezone.utc)
    )

    try:
        session.add(new_intake)
        session.commit()
        session.refresh(new_intake)

        logger.info(f"Intake created: {new_intake.id}")
        return new_intake

    except Exception as e:
        session.rollback()
        logger.error(f"Error creating intake: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to mark intake"
        )


@router.get(
    "/intakes/today",
    response_model=List[IntakeResponse],
    summary="Get today's intakes"
)
def get_today_intakes(
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Get medication intakes for today"""
    today = get_current_utc_date()

    intakes = session.exec(
        select(MedicationIntake).where(
            and_(
                MedicationIntake.user_id == current_user.id,
                MedicationIntake.intake_date == today
            )
        ).order_by(MedicationIntake.taken)
    ).all()

    logger.info(f"Retrieved {len(intakes)} intakes for today for user {current_user.id}")
    return intakes

risk_service = RiskService()


@router.get(
    "/risk",
    response_model=RiskResponse,
    summary="Get today's risk score"
)
def get_today_risk(
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    today = datetime.now(timezone.utc).date()

    return risk_service.calculate_and_save(
        session,
        current_user.id,
        today
    )


@router.get(
    "/history",
    response_model=List[RiskResponse]
)
def get_risk_history(
        days: int = Query(30, ge=1, le=365),
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    from datetime import timedelta

    start_date = datetime.now(timezone.utc).date() - timedelta(days=days)

    return session.exec(
        select(RiskScore).where(
            RiskScore.user_id == current_user.id,
            RiskScore.risk_date >= start_date
        ).order_by(RiskScore.risk_date.desc())
    ).all()


@router.post(
    "/context/update",
    summary="Обновить контекст дня (погодные данные)",
    description="Автоматически получает и сохраняет погодные данные для местоположения пользователя"
)
async def update_daily_context(
        latitude: Optional[float] = Query(None, description="Широта местоположения"),
        longitude: Optional[float] = Query(None, description="Долгота местоположения"),
        city_name: Optional[str] = Query(None, description="Название города (альтернатива координатам)"),
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Обновляет контекст дня с погодными данными"""
    today = get_current_utc_date()

    # Если координаты не указаны, пытаемся получить по названию города
    if latitude is None or longitude is None:
        if city_name:
            try:
                geolocator = Nominatim(user_agent="chroncare_app")
                location = geolocator.geocode(city_name, timeout=10)
                if location:
                    latitude, longitude = location.latitude, location.longitude
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Не удалось определить координаты города"
                    )
            except GeocoderTimedOut:
                raise HTTPException(
                    status_code=408,
                    detail="Таймаут при определении местоположения"
                )
        else:
            raise HTTPException(
                status_code=400,
                detail="Укажите либо координаты (latitude, longitude), либо название города"
            )

    # Получаем погодные данные
    weather_data = await WeatherService.fetch_weather_data(latitude, longitude)

    if not weather_data:
        raise HTTPException(
            status_code=500,
            detail="Не удалось получить погодные данные"
        )

    # Проверяем существующую запись за сегодня
    existing_context = session.exec(
        select(DailyContext).where(
            DailyContext.user_id == current_user.id,
            DailyContext.context_date == today
        )
    ).first()

    if existing_context:
        # Обновляем существующую запись
        existing_context.temperature = weather_data["temperature"]
        existing_context.humidity = weather_data["humidity"]
        existing_context.pollen_index = weather_data["pollen_index"]
        existing_context.air_quality_index = weather_data["air_quality_index"]

        session.add(existing_context)
        context_record = existing_context
    else:
        # Создаем новую запись
        context_record = DailyContext(
            user_id=current_user.id,
            context_date=today,
            temperature=weather_data["temperature"],
            humidity=weather_data["humidity"],
            pollen_index=weather_data["pollen_index"],
            air_quality_index=weather_data["air_quality_index"]
        )
        session.add(context_record)

    try:
        session.commit()
        session.refresh(context_record)

        logger.info(f"Weather context updated for user {current_user.id}")

        return {
            "status": "success",
            "message": "Контекст дня обновлен",
            "date": today.isoformat(),
            "data": {
                "temperature": context_record.temperature,
                "humidity": context_record.humidity,
                "pollen_index": context_record.pollen_index,
                "air_quality_index": context_record.air_quality_index
            }
        }

    except Exception as e:
        session.rollback()
        logger.error(f"Error saving context: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка сохранения данных: {str(e)}"
        )