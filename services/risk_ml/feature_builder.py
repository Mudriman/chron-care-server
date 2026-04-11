from datetime import date, timedelta
from sqlmodel import Session, select, and_

from app.db.models import SymptomEntry, DailyContext, MedicationIntake, Medication



class FeatureBuilder:
    def __init__(self, session: Session):
        self.session = session

    def build(self, user_id: int, target_date: date) -> dict:
        features = {}

        # -------------------
        # SYMPTOMS (3 дня)
        # -------------------
        symptoms = self._get_symptoms(user_id, target_date)

        features["symptom_today"] = symptoms[0]
        features["symptom_lag1"] = symptoms[1]
        features["symptom_lag2"] = symptoms[2]

        # -------------------
        # RELIEVER
        # -------------------
        reliever = self._get_reliever_usage(user_id, target_date)

        features["reliever_use_today"] = reliever[0]
        features["reliever_use_lag1"] = reliever[1]
        features["reliever_use_lag2"] = reliever[2]
        features["reliever_use_3day_avg"] = sum(reliever) / 3

        # -------------------
        # CONTEXT
        # -------------------
        ctx = self._get_context(user_id, target_date)

        features.update(ctx)

        return features

    # =========================
    # HELPERS
    # =========================

    def _get_symptoms(self, user_id, target_date):
        result = []

        for i in range(3):
            d = target_date - timedelta(days=i)

            entry = self.session.exec(
                select(SymptomEntry).where(
                    and_(
                        SymptomEntry.user_id == user_id,
                        SymptomEntry.symptom_date == d
                    )
                )
            ).first()

            if entry:
                val = entry.cough + entry.breathlessness + (2 if entry.night_symptoms else 0)
            else:
                val = 0

            result.append(val)

        return result

    def _get_reliever_usage(self, user_id, target_date):
        result = []

        for i in range(3):
            d = target_date - timedelta(days=i)

            count = self.session.exec(
                select(MedicationIntake)
                .join(Medication)
                .where(
                    and_(
                        MedicationIntake.user_id == user_id,
                        MedicationIntake.intake_date == d,
                        MedicationIntake.taken == True,
                        Medication.name.ilike('%reliever%')
                    )
                )
            ).all()

            result.append(len(count))

        return result

    def _get_context(self, user_id, target_date):
        def get_day(d):
            ctx = self.session.exec(
                select(DailyContext).where(
                    and_(
                        DailyContext.user_id == user_id,
                        DailyContext.context_date == d
                    )
                )
            ).first()

            if not ctx:
                return 0, 0, 0, 0, 0, 0

            extra = ctx.extra_data or {}

            return (
                ctx.temperature or 0,
                ctx.humidity or 0,
                ctx.air_quality_index or 0,
                extra.get("grass_pollen", 0),
                extra.get("tree_pollen", 0),
                extra.get("weed_pollen", 0),
            )

        today = get_day(target_date)
        yesterday = get_day(target_date - timedelta(days=1))

        return {
            "temperature_today": today[0],
            "temperature_lag1": yesterday[0],

            "humidity_today": today[1],
            "humidity_lag1": yesterday[1],

            "pm25_today": today[2],
            "pm25_lag1": yesterday[2],

            "grass_pollen": today[3],
            "tree_pollen": today[4],
            "weed_pollen": today[5],
        }