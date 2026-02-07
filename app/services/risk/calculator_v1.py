# app/services/risk/calculator_v1.py
from app.services.risk.context_builder import RiskContext


class RiskCalculatorV1:
    VERSION = "formula_v1"

    def calculate(self, ctx: RiskContext):
        score = 0.0
        factors = {}

        # --- симптомы (60%) ---
        symptom_score = (
                                ctx.cough +
                                ctx.breathlessness +
                                (2 if ctx.night_symptoms else 0)
                        ) / 8.0  # макс 8 баллов

        score += symptom_score * 0.6
        factors["symptoms"] = round(symptom_score, 3)

        # --- комплаенс (30%) ---
        adherence_penalty = 1 - ctx.medication_adherence
        score += adherence_penalty * 0.3
        factors["adherence"] = round(adherence_penalty, 3)

        # --- погода (10%) ---
        weather_score = self._calculate_weather_score(ctx)
        score += weather_score * 0.1
        factors["weather"] = round(weather_score, 3)

        # Ограничиваем 0-1
        score = max(0.0, min(score, 1.0))

        return score, factors

    def _calculate_weather_score(self, ctx: RiskContext) -> float:

        score = 0.0

        # Пыльца (0-10): >7 = 0.5, >4 = 0.3
        if ctx.pollen_index:
            if ctx.pollen_index > 7:
                score += 0.5
            elif ctx.pollen_index > 4:
                score += 0.3
            elif ctx.pollen_index > 2:
                score += 0.1

        # Качество воздуха (0-500): >150 = 0.5, >100 = 0.3
        if ctx.air_quality_index:
            if ctx.air_quality_index > 150:
                score += 0.5
            elif ctx.air_quality_index > 100:
                score += 0.3
            elif ctx.air_quality_index > 50:
                score += 0.1

        return min(score, 1.0)