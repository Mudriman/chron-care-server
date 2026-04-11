# app/services/risk/risk_service.py
from datetime import date
from typing import List
from sqlmodel import Session, select, and_

from app.db.models import RiskScore
from app.services.risk.context_builder import build_risk_context, RiskContext
from app.services.risk.calculator_v1 import RiskCalculatorV1


class RiskService:
    def __init__(self):
        self.calculator = RiskCalculatorV1()

    def calculate_and_save(
            self,
            session: Session,
            user_id: int,
            target_date: date
    ) -> RiskScore:
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

        ctx = build_risk_context(session, user_id, target_date)
        score, factors = self.calculator.calculate(ctx)

        risk = RiskScore(
            user_id=user_id,
            risk_date=target_date,
            risk_value=score,
            risk_level=self._level(score),
            model_version=self.calculator.VERSION,
            confidence=self._calculate_confidence(ctx),
            factors=factors,
            recommendations=self._recommendations(score, factors, ctx)
        )

        session.add(risk)
        session.commit()
        session.refresh(risk)

        return risk

    def _level(self, score: float) -> str:
        if score < 0.3:
            return "low"
        if score < 0.6:
            return "medium"
        return "high"

    def _calculate_confidence(self, ctx: RiskContext) -> float:
        if ctx.cough > 0 or ctx.breathlessness > 0 or ctx.night_symptoms:
            return 0.9
        return 0.7

    def _recommendations(self, score: float, factors: dict, ctx: RiskContext) -> List[str]:
        recommendations = []

        # По симптомам
        if factors.get("symptoms", 0) > 0.5:
            recommendations.append("Severe symptoms. Consultation with a doctor is recommended.")
        elif factors.get("symptoms", 0) > 0.2:
            recommendations.append('Moderate symptoms. Increase monitoring.')
        else:
            recommendations.append("Symptoms are normal.")

        # По комплаенсу
        if factors.get("adherence", 0) > 0.3:
            recommendations.append(f"{int(factors['adherence'] * 100)}% of doses were missed. It is important to follow the schedule.")

        # По риску
        if score >= 0.6:
            recommendations.append("HIGH RISK! Contact your doctor.")
        elif score >= 0.3:
            recommendations.append("Medium risk. Please be careful.")
        else:
            recommendations.append("The risk is low. Continue treatment.")

        return recommendations