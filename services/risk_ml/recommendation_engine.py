# -*- coding: utf-8 -*-

from typing import Dict, List


class RecommendationEngine:

    @staticmethod
    def generate(
            risk_prob: float,
            risk_level: str,
            features: Dict = None,
            shap_factors: Dict = None,
            confidence: float = None
    ) -> List[str]:

        recommendations = []

        # ==========================================
        # 1. ГЛАВНАЯ РЕКОМЕНДАЦИЯ ПО СИЛЕ РИСКА
        # ==========================================
        if risk_prob > 0.7:
            recommendations.append(
                "Высокий риск обострения в ближайшие сутки — рассмотрите консультацию врача"
            )
        elif risk_prob > 0.4:
            recommendations.append(
                "Есть вероятность ухудшения — усилите контроль состояния"
            )
        else:
            recommendations.append(
                "Риск низкий — продолжайте текущую терапию"
            )

        # ==========================================
        # 2. ЧЕСТНОСТЬ СИСТЕМЫ (confidence)
        # ==========================================
        if confidence is not None:
            if confidence < 0.6:
                recommendations.append(
                    "Прогноз имеет умеренную точность — ориентируйтесь также на самочувствие"
                )
            elif confidence < 0.4:
                recommendations.append(
                    "Прогноз имеет низкую точность — больше доверяйте своим ощущениям"
                )

        # ==========================================
        # 3. АНАЛИЗ ТОП-2 ФАКТОРОВ SHAP
        # ==========================================
        if shap_factors:
            # Сортируем факторы по влиянию
            sorted_factors = sorted(
                shap_factors.items(),
                key=lambda x: abs(x[1]),
                reverse=True
            )[:2]  # Берем топ-2

            for factor_name, factor_value in sorted_factors:
                # Пропускаем незначимые факторы
                if abs(factor_value) < 0.12:
                    continue

                # ПОЛОЖИТЕЛЬНОЕ ВЛИЯНИЕ (увеличивает риск)
                if factor_value > 0.15:
                    if factor_name == "symptoms":
                        recommendations.append(
                            "Обратите внимание на усиление симптомов — при необходимости используйте план действий"
                        )
                    elif factor_name == "adherence":
                        recommendations.append(
                            "Проверьте регулярность приема препаратов — это критично для контроля заболевания"
                        )
                    elif factor_name == "weather":
                        recommendations.append(
                            "Избегайте длительного пребывания на улице из-за неблагоприятных погодных условий"
                        )

                # ОТРИЦАТЕЛЬНОЕ ВЛИЯНИЕ (снижает риск)
                elif factor_value < -0.15:
                    if factor_name == "symptoms":
                        recommendations.append(
                            "Хороший контроль симптомов — продолжайте в том же духе"
                        )
                    elif factor_name == "adherence":
                        recommendations.append(
                            "Отличная приверженность терапии — это снижает риск обострения"
                        )
                    elif factor_name == "weather":
                        recommendations.append(
                            "Погодные условия сегодня благоприятны — можно больше гулять"
                        )

        # ==========================================
        # 4. КОНТЕКСТНАЯ БАЗОВАЯ РЕКОМЕНДАЦИЯ
        # ==========================================
        if risk_level != "low":
            recommendations.append(
                "Запишите симптомы сегодня — это поможет отследить динамику"
            )
        else:
            recommendations.append(
                "Продолжайте вести дневник симптомов для точного прогноза"
            )

        # ==========================================
        # 5. Убираем дубликаты, но сохраняем порядок
        # ==========================================
        seen = set()
        unique_recs = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recs.append(rec)

        # Ограничиваем 5-ю рекомендациями (не перегружаем UI)
        return unique_recs[:5]