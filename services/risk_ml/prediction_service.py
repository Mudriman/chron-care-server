import joblib
import numpy as np
from datetime import date
from sqlmodel import Session, select, and_

from app.db.models import RiskScore
from .feature_builder import FeatureBuilder
from .constants import FEATURE_COLUMNS


class PredictionService:
    VERSION = "rf_24h_v1"

    def __init__(self, model_path: str):
        self.model = joblib.load(model_path)

    def predict_and_save(self, session: Session, user_id: int, target_date: date):
        # -------------------------
        # 1. Удаляем старый скор
        # -------------------------
        existing = session.exec(
            select(RiskScore).where(
                and_(
                    RiskScore.user_id == user_id,
                    RiskScore.risk_date == target_date
                )
            )
        ).first()

        if existing:
            session.delete(existing)
            session.commit()

        # -------------------------
        # 2. Собираем фичи
        # -------------------------
        builder = FeatureBuilder(session)
        features = builder.build(user_id, target_date)

        X = np.array([[features[col] for col in FEATURE_COLUMNS]])

        # -------------------------
        # 3. Предсказание
        # -------------------------
        proba = float(self.model.predict_proba(X)[0][1])

        # -------------------------
        # 4. Формируем ответ
        # -------------------------
        risk = RiskScore(
            user_id=user_id,
            risk_date=target_date,
            risk_value=proba,
            risk_level=self._level(proba),
            model_version=self.VERSION,
            confidence=self._confidence(proba),
            factors=self._build_factors(features),
            recommendations=self._recommendations(proba, features)
        )

        session.add(risk)
        session.commit()
        session.refresh(risk)

        return risk

    # =========================
    # HELPERS
    # =========================

    def _level(self, p: float):
        if p < 0.3:
            return "low"
        elif p < 0.6:
            return "medium"
        return "high"

    def _confidence(self, p: float):
        return max(p, 1 - p)

    def _build_factors(self, features: dict):
        return {
            "symptoms": round(features["symptom_today"] / 10, 3),
            "adherence": round(1 - features["reliever_use_3day_avg"], 3),
            "weather": round(features["pm25_today"] / 100, 3)
        }

    def _recommendations(self, score: float, features: dict):
        recs = []

        # симптомы
        if features["symptom_today"] > 5:
            recs.append("Severe symptoms. Consultation with a doctor is recommended.")
        elif features["symptom_today"] > 2:
            recs.append("Moderate symptoms. Increase monitoring.")
        else:
            recs.append("Symptoms are normal.")

        # комплаенс
        if features["reliever_use_3day_avg"] > 0.5:
            recs.append("Frequent reliever use. Review your treatment plan.")

        # риск
        if score >= 0.6:
            recs.append("HIGH RISK! Contact your doctor.")
        elif score >= 0.3:
            recs.append("Medium risk. Please be careful.")
        else:
            recs.append("The risk is low. Continue treatment.")

        return recs