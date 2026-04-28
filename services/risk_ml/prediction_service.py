import joblib
import numpy as np
import pandas as pd
from datetime import date
from sqlmodel import Session, select, and_
import shap

from app.db.models import RiskScore
from .feature_builder import FeatureBuilder
from .constants import FEATURE_COLUMNS
from .recommendation_engine import RecommendationEngine


class PredictionService:
    VERSION = "rf_24h_v1"

    def __init__(self, model_path: str):
        self.model = joblib.load(model_path)

        # Initialize SHAP TreeExplainer for the RandomForest model
        try:
            self.explainer = shap.TreeExplainer(self.model)
            print(f"SHAP explainer initialized successfully")
        except Exception as e:
            print(f"Warning: SHAP explainer initialization failed: {e}")
            self.explainer = None

    def predict_and_save(self, session: Session, user_id: int, target_date: date):
        # -------------------------
        # 1. Delete old score
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
        # 2. Build features
        # -------------------------
        builder = FeatureBuilder(session)
        features = builder.build(user_id, target_date)

        # CRITICAL: Use DataFrame instead of numpy array
        X = pd.DataFrame([features], columns=FEATURE_COLUMNS)

        # -------------------------
        # 3. Prediction
        # -------------------------
        proba = float(self.model.predict_proba(X)[0][1])

        # Convert to integer percentage for API (0-100)
        risk_score_int = int(round(proba * 100))

        # -------------------------
        # 3.5. SHAP values for explainability
        # -------------------------
        shap_values_dict = None
        if self.explainer is not None:
            try:
                # Compute SHAP values
                shap_values = self.explainer.shap_values(X)

                # Debug: print shape and type
                print(f"SHAP values type: {type(shap_values)}")
                print(f"SHAP array shape: {shap_values.shape}")

                # Handle 3D array shape: (n_samples, n_features, n_classes)
                if len(shap_values.shape) == 3:
                    # For binary classification, take class 1 (index 1)
                    # Result shape: (n_samples, n_features)
                    shap_array_2d = shap_values[:, :, 1]
                    # Take first sample (since we have only one)
                    shap_array = shap_array_2d[0]
                elif len(shap_values.shape) == 2:
                    # 2D array: (n_samples, n_features)
                    shap_array = shap_values[0]
                elif len(shap_values.shape) == 1:
                    # 1D array: (n_features,)
                    shap_array = shap_values
                else:
                    raise ValueError(f"Unexpected SHAP shape: {shap_values.shape}")

                print(f"Processed SHAP array shape: {shap_array.shape}")
                print(f"Expected features count: {len(FEATURE_COLUMNS)}")

                # CRITICAL: Validate shape before using
                if len(shap_array) != len(FEATURE_COLUMNS):
                    print(f"ERROR: SHAP shape mismatch! Expected {len(FEATURE_COLUMNS)}, got {len(shap_array)}")
                    shap_values_dict = None
                else:
                    # Map SHAP values to feature names
                    shap_values_dict = {
                        feature: float(shap_array[i])
                        for i, feature in enumerate(FEATURE_COLUMNS)
                    }
                    print(f"SHAP values computed successfully for user {user_id}")
                    print(f"Sample SHAP values (first 3): {list(shap_values_dict.items())[:3]}")

            except Exception as e:
                print(f"Warning: SHAP computation failed for user {user_id}: {e}")
                import traceback
                traceback.print_exc()
                shap_values_dict = None
        else:
            print(f"SHAP explainer not available for user {user_id}")

        # -------------------------
        # 4. Build response
        # -------------------------
        risk = RiskScore(
            user_id=user_id,
            risk_date=target_date,
            risk_value=risk_score_int,  # Now integer 0-100 instead of float
            risk_level=self._level(proba),
            model_version=self.VERSION,
            confidence=self._confidence(proba),
            factors=self._build_factors(features, shap_values_dict),
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
        if p < 0.4:
            return "low"
        elif p < 0.7:
            return "medium"
        return "high"

    def _confidence(self, p: float):
        return max(p, 1 - p)

    def _build_factors(self, features: dict, shap_values_dict: dict = None):
        """
        Build factor contributions for the response.

        Uses SHAP values for real model explainability.
        Falls back to heuristic logic only if SHAP fails.
        """

        # Use SHAP if available
        if shap_values_dict is not None:
            # Group 1: Symptoms
            symptom_features = [
                "symptom_today",
                "symptom_lag1",
                "symptom_lag2"
            ]
            symptoms_sum = sum(shap_values_dict.get(f, 0.0) for f in symptom_features)

            # Group 2: Adherence (reliever medication usage)
            adherence_features = [
                "reliever_use_today",
                "reliever_use_lag1",
                "reliever_use_lag2",
                "reliever_use_3day_avg"
            ]
            adherence_sum = sum(shap_values_dict.get(f, 0.0) for f in adherence_features)

            # Group 3: Weather and environmental factors
            weather_features = [
                "pm25_today",
                "pm25_lag1",
                "humidity_today",
                "humidity_lag1",
                "temperature_today",
                "temperature_lag1",
                "grass_pollen",
                "tree_pollen",
                "weed_pollen"
            ]
            weather_sum = sum(shap_values_dict.get(f, 0.0) for f in weather_features)

            print(
                f"Raw SHAP sums - symptoms: {symptoms_sum:.4f}, adherence: {adherence_sum:.4f}, weather: {weather_sum:.4f}")

            # Normalize for UI stability
            total_abs_impact = abs(symptoms_sum) + abs(adherence_sum) + abs(weather_sum)

            if total_abs_impact > 1e-6:
                # Normalized contributions that preserve sign
                result = {
                    "symptoms": round(symptoms_sum / total_abs_impact, 4),
                    "adherence": round(adherence_sum / total_abs_impact, 4),
                    "weather": round(weather_sum / total_abs_impact, 4)
                }
            else:
                # Raw values if total impact is zero
                result = {
                    "symptoms": round(symptoms_sum, 4),
                    "adherence": round(adherence_sum, 4),
                    "weather": round(weather_sum, 4)
                }

            print(f"Normalized factors: {result}")
            return result

        # Fallback to heuristic logic (only if SHAP completely fails)
        print("Using fallback heuristic logic for factors")
        return {
            "symptoms": round(features["symptom_today"] / 10, 3),
            "adherence": round(1 - features["reliever_use_3day_avg"], 3),
            "weather": round(features["pm25_today"] / 100, 3)
        }

    def _recommendations(self, proba: float, features: dict, shap_values_dict: dict = None) -> list:
        risk_level = self._level(proba)
        confidence = self._confidence(proba)

        return RecommendationEngine.generate(
            risk_prob=proba,
            risk_level=risk_level,
            features=features,
            shap_factors=shap_values_dict,
            confidence = confidence
        )