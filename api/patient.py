# -*- coding: utf-8 -*-

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlmodel import Session, select, and_
from typing import List, Optional
import logging
from datetime import timedelta, datetime, timezone

from app.db.session import get_session
from app.db.models import User, Medication, SymptomEntry, MedicationIntake, get_current_utc_date, RiskScore, \
    DailyContext, ExacerbationEvent
from app.core.dependencies import get_current_patient
from app.schemas.exacerbation import ExacerbationResponse, ExacerbationCreate
from app.schemas.medication import MedicationCreate, MedicationResponse, MedicationUpdate
from app.schemas.symptom import SymptomCreate, SymptomResponse
from app.schemas.intake import IntakeCreate, IntakeResponse
from app.services.risk.risk_service import RiskService
from app.schemas.risk import RiskResponse
from app.services.weather.weather_service import WeatherService

from app.services.intakes.intake_stats_service import IntakeStatsService
from app.services.intakes.intake_stats_calculator import IntakeStatsCalculator
from app.schemas.intake_stats import IntakeStatsResponse, PeriodStats, TodayStats, ChartDataPoint

from app.services.risk_ml.prediction_service import PredictionService
from app.services.risk_ml.schemas import RiskMLResponse

from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

logger = logging.getLogger(__name__)
router = APIRouter()

ml_service = PredictionService("app/models/rf_model.pkl")


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
        logger.info(f"Notes: {new_medication.notes}, Notifications: {new_medication.notifications_enabled}")
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


@router.patch(
    "/meds/{medication_id}",
    response_model=MedicationResponse,
    summary="Update medication"
)
def update_medication(
        medication_id: int,
        medication_data: MedicationUpdate,  # Используем специальную схему для обновления
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """
    Update medication details.

    This endpoint supports partial updates - you can send only the fields you want to change.
    Examples:
    - Update only notes: {"notes": "New notes text"}
    - Toggle notifications: {"notifications_enabled": false}
    - Update multiple fields: {"notes": "New notes", "notifications_enabled": true, "dosage": "200mg"}
    """
    logger.info(f"Updating medication {medication_id} for user {current_user.id}")

    # Получаем лекарство
    medication = session.get(Medication, medication_id)

    if not medication:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Medication not found"
        )

    # Проверяем права доступа
    if medication.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot update medication of another user"
        )

    # Получаем только те поля, которые были отправлены
    update_data = medication_data.dict(exclude_unset=True)

    # Если ничего не отправлено - возвращаем ошибку
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )

    # Логируем, что именно обновляем
    logger.info(f"Updating fields: {list(update_data.keys())}")

    # Обновляем только переданные поля
    for field, value in update_data.items():
        setattr(medication, field, value)

    try:
        session.add(medication)
        session.commit()
        session.refresh(medication)

        logger.info(f"Medication {medication_id} updated successfully")

        # Дополнительное логирование для специфических полей
        if 'notes' in update_data:
            logger.info(f"Notes updated for medication {medication_id}")
        if 'notifications_enabled' in update_data:
            logger.info(
                f"Notifications toggled to {update_data['notifications_enabled']} for medication {medication_id}")

        return medication

    except Exception as e:
        session.rollback()
        logger.error(f"Error updating medication {medication_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update medication"
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
    """Mark medication intake for today - creates a new record for each intake"""
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

    # Просто создаем новую запись для каждого приема
    new_intake = MedicationIntake(
        user_id=current_user.id,
        medication_id=intake_data.medication_id,
        intake_date=intake_date,
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


@router.get("/intakes/stats", response_model=IntakeStatsResponse, summary="Get intake statistics")
def get_intake_stats(
        days: int = Query(30, ge=1, le=365, description="Number of days for statistics"),
        current_user=Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    """Get medication intake statistics for the specified period"""
    # Получаем id пользователя (в вашей модели User есть поле id)
    user_id = current_user.id

    logger.info(f"Fetching intake stats for user {user_id} for last {days} days")

    # Инициализация сервисов
    stats_service = IntakeStatsService(session, user_id)
    calculator = IntakeStatsCalculator()

    # Расчет дат
    cutoff_date = get_current_utc_date() - timedelta(days=days)
    today = get_current_utc_date()

    # Получение данных
    medications = stats_service.get_medications()
    intakes = stats_service.get_intakes(cutoff_date)

    # Если нет данных, возвращаем пустую статистику
    if not medications:
        return IntakeStatsResponse(
            period=PeriodStats(
                days=days,
                total_taken=0,
                total_scheduled=0,
                adherence_rate=0,
                best_streak=0,
                current_streak=0
            ),
            today=TodayStats(taken=0, scheduled=0, progress=0),
            chart=[]
        )

    # Обработка данных
    calculator.process_intakes(intakes)
    total_scheduled, daily_scheduled = calculator.calculate_scheduled_intakes(
        medications, cutoff_date, today
    )

    total_taken = sum(calculator.taken_by_date.values())
    adherence_rate = round((total_taken / total_scheduled * 100), 1) if total_scheduled > 0 else 0

    current_streak, best_streak = calculator.calculate_streaks(
        daily_scheduled, calculator.taken_by_date, today, days
    )

    # Формирование ответа
    return IntakeStatsResponse(
        period=PeriodStats(
            days=days,
            total_taken=total_taken,
            total_scheduled=total_scheduled,
            adherence_rate=adherence_rate,
            best_streak=best_streak,
            current_streak=current_streak
        ),
        today=TodayStats(**calculator.get_today_stats(today, daily_scheduled)),
        chart=[ChartDataPoint(**item) for item in calculator.prepare_chart_data(daily_scheduled)]
    )

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

@router.get("/risk-ml", response_model=RiskResponse)
def get_today_risk_ml(
    current_user = Depends(get_current_patient),
    session: Session = Depends(get_session)
):
    today = datetime.now(timezone.utc).date()

    return ml_service.predict_and_save(
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


@router.get("/context/today")
async def get_today_context(
        city: str = Query(None, description="Город"),
        lat: float = Query(None, description="Широта"),
        lon: float = Query(None, description="Долгота"),
        current_user: User = Depends(get_current_patient),
        session: Session = Depends(get_session)
):
    import logging
    import json
    from datetime import datetime
    logger = logging.getLogger(__name__)

    logger.info(f"=== GET TODAY CONTEXT ===")
    logger.info(f"User ID: {current_user.id}, city: {city}, lat: {lat}, lon: {lon}")
    print(f"\n🔥🔥🔥 WeatherService.get_context CALLED for {lat}, {lon} 🔥🔥🔥\n")
    # 1. Определяем координаты
    if not lat or not lon:
        if not city:
            raise HTTPException(400, "Нужен город или координаты")
        try:
            geolocator = Nominatim(user_agent="chroncare_mvp")
            location = geolocator.geocode(city, timeout=5)
            if not location:
                raise HTTPException(400, f"Город '{city}' не найден")
            lat, lon = location.latitude, location.longitude
            logger.info(f"Geocoded: {city} -> {lat}, {lon}")
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
            raise

    today = get_current_utc_date()

    # 2. Проверяем кэш
    context = session.exec(
        select(DailyContext).where(
            DailyContext.user_id == current_user.id,
            DailyContext.context_date == today
        )
    ).first()

    if context and context.extra_data and context.extra_data.get("city") == city:
        logger.info("Found in DB, returning cached data")
        return {
            "date": today,
            "data": {
                "temperature": context.temperature,
                "humidity": context.humidity,
                "air_quality_index": context.air_quality_index,
                "pollen_index": context.pollen_index,
                "pollen_details": context.extra_data.get("pollen_details", {}),
                "forecast": context.extra_data.get("forecast", {})
            }
        }

    # 3. Получаем свежие данные (теперь они уже чище)
    logger.info(f"Fetching fresh data for {city or f'lat={lat},lon={lon}'}")
    weather_data = await WeatherService.get_context(lat, lon)

    if not weather_data:
        raise HTTPException(503, "Сервис погоды временно недоступен")

    # 4. Сохраняем в БД
    extra_data = {
        "city": city or "по координатам",
        "coordinates": weather_data.pop("coordinates", {"lat": lat, "lon": lon}),
        "pollen_details": weather_data.pop("pollen_details", {}),
        "forecast": weather_data.pop("forecast", {}),
        "source": weather_data.pop("source", "open-meteo"),
        "timestamp": weather_data.pop("timestamp", datetime.utcnow().isoformat())
    }

    if context:
        context.temperature = weather_data["temperature"]
        context.humidity = weather_data["humidity"]
        context.air_quality_index = weather_data["air_quality_index"]
        context.pollen_index = weather_data["pollen_index"]
        context.extra_data = extra_data
        logger.info("Updating existing record")
    else:
        context = DailyContext(
            user_id=current_user.id,
            context_date=today,
            temperature=weather_data["temperature"],
            humidity=weather_data["humidity"],
            air_quality_index=weather_data["air_quality_index"],
            pollen_index=weather_data["pollen_index"],
            extra_data=extra_data
        )
        session.add(context)
        logger.info("Creating new record")

    session.commit()

    # 5. Возвращаем данные (теперь структура чище)
    return {
        "date": today,
        "data": {
            "temperature": weather_data["temperature"],
            "humidity": weather_data["humidity"],
            "air_quality_index": weather_data["air_quality_index"],
            "pollen_index": weather_data["pollen_index"],
            "pollen_details": extra_data["pollen_details"],
            "forecast": extra_data["forecast"]
        }
    }

@router.post("/exacerbations", response_model=ExacerbationResponse)
def create_exacerbation(
    data: ExacerbationCreate,
    current_user: User = Depends(get_current_patient),
    session: Session = Depends(get_session)
):
    event = ExacerbationEvent(
        user_id=current_user.id,
        event_date=data.event_date or get_current_utc_date(),
        severity=data.severity,
        triggered_by=data.triggered_by
    )

    session.add(event)
    session.commit()
    session.refresh(event)

    return event

@router.get("/exacerbations", response_model=list[ExacerbationResponse])
def get_my_exacerbations(
    current_user: User = Depends(get_current_patient),
    session: Session = Depends(get_session)
):
    exacerbations = session.exec(
        select(ExacerbationEvent)
        .where(ExacerbationEvent.user_id == current_user.id)
        .order_by(ExacerbationEvent.event_date.desc())
    ).all()
    return exacerbations