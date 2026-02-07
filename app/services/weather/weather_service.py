# -*- coding: utf-8 -*-

import httpx
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)


class WeatherService:
    """Сервис для получения данных о погоде с Open-Meteo API"""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    @staticmethod
    async def fetch_weather_data(latitude: float, longitude: float) -> Optional[Dict]:
        """
        Получает текущие погодные данные по координатам

        Args:
            latitude: Широта
            longitude: Долгота

        Returns:
            Словарь с температурой и влажностью, или None в случае ошибки
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m",
            "timezone": "auto",
            "forecast_days": 1
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(WeatherService.BASE_URL, params=params)
                response.raise_for_status()
                data = response.json()

                return {
                    "temperature": data["current"].get("temperature_2m"),
                    "humidity": data["current"].get("relative_humidity_2m"),
                    # Open-Meteo не предоставляет pollen_index и air_quality_index
                    # Их можно получить из других API или оставить None
                    "pollen_index": None,
                    "air_quality_index": None,
                    "raw_data": data  # Сохраняем сырые данные на всякий случай
                }

        except Exception as e:
            logger.error(f"Error fetching weather data: {str(e)}")
            return None