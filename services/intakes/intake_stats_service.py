# services/intake_stats_service.py
from datetime import date, timedelta
from typing import List
from sqlmodel import Session, select
from sqlalchemy import and_

from app.db.models import Medication, MedicationIntake  # импортируем из вашего файла моделей


class IntakeStatsService:
    def __init__(self, session: Session, user_id: int):
        self.session = session
        self.user_id = user_id

    def get_medications(self) -> List[Medication]:
        statement = select(Medication).where(
            and_(
                Medication.user_id == self.user_id,
                Medication.is_active == True
            )
        )
        result = self.session.exec(statement)
        medications = result.all()
        return list(medications) if medications else []

    def get_intakes(self, cutoff_date: date) -> List[MedicationIntake]:
        statement = select(MedicationIntake).where(
            and_(
                MedicationIntake.user_id == self.user_id,
                MedicationIntake.intake_date >= cutoff_date
            )
        ).order_by(MedicationIntake.intake_date)
        result = self.session.exec(statement)
        intakes = result.all()
        return list(intakes) if intakes else []