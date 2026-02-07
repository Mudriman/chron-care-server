# app/services/risk/context_builder.py
import logging
from sqlmodel import Session, select, and_
from datetime import date, timedelta
from pydantic import BaseModel, Field, validator
from typing import Optional
from app.db.models import SymptomEntry, Medication, MedicationIntake, DailyContext

logger = logging.getLogger(__name__)


class RiskContext(BaseModel):
    cough: int = Field(ge=0, le=3)
    breathlessness: int = Field(ge=0, le=3)
    night_symptoms: bool
    medication_adherence: float = Field(ge=0, le=1)  # 0..1
    temperature: Optional[float] = Field(None, ge=-50, le=60)
    humidity: Optional[float] = Field(None, ge=0, le=100)
    pollen_index: Optional[float] = Field(None, ge=0, le=10)
    air_quality_index: Optional[float] = Field(None, ge=0, le=500)

    @validator('medication_adherence')
    def validate_adherence(cls, v):
        return max(0.0, min(1.0, v))


def build_risk_context(
        session: Session,
        user_id: int,
        target_date: date,
        adherence_days: int = 3  # Параметр: за сколько дней считать комплаенс
) -> RiskContext:
    """Построить контекст риска для пользователя на указанную дату"""

    logger.info(f"Building risk context for user {user_id}, date {target_date}")

    # ---------- 1. СИМПТОМЫ (сегодня или последние доступные) ----------
    symptom = session.exec(
        select(SymptomEntry).where(
            and_(
                SymptomEntry.user_id == user_id,
                SymptomEntry.symptom_date == target_date
            )
        )
    ).first()

    if symptom:
        cough = symptom.cough
        breathlessness = symptom.breathlessness
        night_symptoms = symptom.night_symptoms
        symptom_source = "today"
    else:
        # Ищем последние симптомы (до 3 дней назад)
        last_symptom = session.exec(
            select(SymptomEntry).where(
                and_(
                    SymptomEntry.user_id == user_id,
                    SymptomEntry.symptom_date < target_date,
                    SymptomEntry.symptom_date >= target_date - timedelta(days=3)
                )
            ).order_by(SymptomEntry.symptom_date.desc())
        ).first()

        if last_symptom:
            cough = last_symptom.cough
            breathlessness = last_symptom.breathlessness
            night_symptoms = last_symptom.night_symptoms
            symptom_source = f"{last_symptom.symptom_date} (cached)"
        else:
            cough = 0
            breathlessness = 0
            night_symptoms = False
            symptom_source = "no data"

    # ---------- 2. КОМПЛАЕНС (за adherence_days дней) ----------
    start_date = target_date - timedelta(days=adherence_days - 1)

    # Активные лекарства на период
    active_meds = session.exec(
        select(Medication).where(
            and_(
                Medication.user_id == user_id,
                Medication.is_active == True,
                # Лекарство должно быть активно в этот период
                (
                        (Medication.start_date <= target_date) &
                        (
                                (Medication.end_date.is_(None)) |
                                (Medication.end_date >= start_date)
                        )
                )
            )
        )
    ).all()

    planned_total = 0
    taken_total = 0

    for med in active_meds:
        # Ожидаемое количество приемов за период
        # Учитываем только дни, когда лекарство было активно
        active_days = adherence_days
        if med.start_date > start_date:
            # Лекарство начали принимать в середине периода
            active_days = (target_date - med.start_date).days + 1

        planned_total += med.frequency_per_day * active_days

        # Фактические приемы
        intakes = session.exec(
            select(MedicationIntake).where(
                and_(
                    MedicationIntake.user_id == user_id,
                    MedicationIntake.medication_id == med.id,
                    MedicationIntake.intake_date >= start_date,
                    MedicationIntake.intake_date <= target_date,
                    MedicationIntake.taken == True
                )
            )
        ).all()

        taken_total += len(intakes)

    # Расчет комплаенса с защитой
    if planned_total == 0:
        adherence = 1.0  # Нет лекарств для приема
    else:
        adherence = min(taken_total / planned_total, 1.0)

    logger.info(f"Adherence: {taken_total}/{planned_total} = {adherence:.2f}")

    # ---------- 3. ПОГОДА (контекст дня) ----------
    context = session.exec(
        select(DailyContext).where(
            and_(
                DailyContext.user_id == user_id,
                DailyContext.context_date == target_date
            )
        )
    ).first()

    temperature = context.temperature if context else None
    humidity = context.humidity if context else None
    pollen_index = context.pollen_index if context else None
    air_quality_index = context.air_quality_index if context else None

    # ---------- 4. СОЗДАНИЕ КОНТЕКСТА ----------
    risk_context = RiskContext(
        cough=cough,
        breathlessness=breathlessness,
        night_symptoms=night_symptoms,
        medication_adherence=adherence,
        temperature=temperature,
        humidity=humidity,
        pollen_index=pollen_index,
        air_quality_index=air_quality_index,
    )

    logger.info(
        f"Context built: symptoms[{symptom_source}]: "
        f"cough={cough}, breath={breathlessness}, night={night_symptoms}, "
        f"adherence={adherence:.2f}, temp={temperature}, humidity={humidity}"
    )

    return risk_context