# services/weather.py
import httpx
from typing import Optional, Dict
import logging
import asyncio
from datetime import datetime
from collections import Counter

logger = logging.getLogger(__name__)


class WeatherService:
    """Улучшенный сервис погоды с поддержкой пыльцы и прогнозом"""

    WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
    AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

    @staticmethod
    async def get_context(lat: float, lon: float) -> Optional[Dict]:
        """
        Получает данные о погоде, качестве воздуха и прогноз на сегодня.
        Возвращает структурированный ответ без лишней вложенности.
        """
        logger.info(f"🔵 WeatherService.get_context called for lat={lat}, lon={lon}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                # Три параллельных запроса
                weather_current, weather_forecast, air = await asyncio.gather(
                    WeatherService._fetch_weather_current(client, lat, lon),
                    WeatherService._fetch_weather_forecast(client, lat, lon),
                    WeatherService._fetch_air_quality(client, lat, lon),
                    return_exceptions=True
                )

                # Обработка ошибок
                if isinstance(weather_current, Exception):
                    logger.warning(f"⚠️ Weather current failed: {weather_current}")
                    weather_current = {}
                if isinstance(weather_forecast, Exception):
                    logger.warning(f"⚠️ Weather forecast failed: {weather_forecast}")
                    weather_forecast = {}
                if isinstance(air, Exception):
                    logger.warning(f"⚠️ Air quality failed: {air}")
                    air = {}

                # Получаем детальные данные о пыльце (уже готовый объект)
                pollen_details = WeatherService._extract_pollen_details(air)

                # Обратно-совместимый индекс
                pollen_index = pollen_details["summary"]["max"] if pollen_details["summary"][
                                                                       "max"] is not None else None

                # Вычисляем прогноз на сегодня
                forecast = WeatherService._calculate_forecast(weather_forecast)
                logger.info(f"📊 Forecast result: {forecast}")

                # Формируем чистый ответ без лишней вложенности
                result = {
                    "temperature": weather_current.get("temp"),
                    "humidity": weather_current.get("humidity"),
                    "air_quality_index": air.get("aqi"),
                    "pollen_index": pollen_index,
                    "pollen_details": pollen_details,  # Прямо на верхнем уровне!
                    "forecast": forecast,
                    "source": "open-meteo",
                    "timestamp": datetime.utcnow().isoformat(),
                    "coordinates": {"lat": lat, "lon": lon}
                }

                logger.info(f"✅ Returning result with forecast: {forecast}")
                return result

            except Exception as e:
                logger.error(f"❌ Failed to get context: {e}")
                return None

    @staticmethod
    async def _fetch_weather_current(client, lat, lon):
        """Получение ТЕКУЩЕЙ погоды"""
        logger.info(f"🔵 Fetching current weather for {lat}, {lon}")

        params = {
            "latitude": lat,
            "longitude": lon,
            "current": ["temperature_2m", "relative_humidity_2m", "weather_code"],
            "timeformat": "unixtime"
        }

        resp = await client.get(WeatherService.WEATHER_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        result = {
            "temp": None,
            "humidity": None,
            "weather_code": None
        }

        if "current" in data:
            result["temp"] = data["current"].get("temperature_2m")
            result["humidity"] = data["current"].get("relative_humidity_2m")
            result["weather_code"] = data["current"].get("weather_code")
            logger.info(f"✅ Current weather: {result}")
        else:
            logger.warning("⚠️ No 'current' in weather response")

        return result

    @staticmethod
    async def _fetch_weather_forecast(client, lat, lon):
        """Получение ПРОГНОЗА погоды на сегодня"""
        logger.info(f"🔵 Fetching forecast for lat={lat}, lon={lon}")

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": ["temperature_2m", "relative_humidity_2m", "weather_code"],
            "forecast_days": 1,
            "timeformat": "unixtime"
        }

        resp = await client.get(WeatherService.WEATHER_URL, params=params)
        logger.info(f"📥 Forecast response status: {resp.status_code}")

        resp.raise_for_status()
        data = resp.json()

        # Логируем первые несколько значений для отладки
        if "hourly" in data:
            temps = data["hourly"].get("temperature_2m", [])[:5]
            logger.info(f"🌡️ First 5 temps: {temps}")

        return data

    @staticmethod
    async def _fetch_air_quality(client, lat, lon):
        """Получение качества воздуха и пыльцы"""
        logger.info(f"🔵 Fetching air quality for {lat}, {lon}")

        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": [
                "european_aqi",
                "birch_pollen",
                "grass_pollen",
                "ragweed_pollen",
                "alder_pollen",
                "olive_pollen",
                "mugwort_pollen"
            ],
            "forecast_days": 1,
            "domains": "cams_europe"
        }

        resp = await client.get(WeatherService.AIR_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        result = {
            "aqi": None,
            "pollens": {}
        }

        if "hourly" in data:
            hourly = data["hourly"]

            # AQI - первый час
            if "european_aqi" in hourly and hourly["european_aqi"]:
                result["aqi"] = hourly["european_aqi"][0]

            # Все виды пыльцы
            pollen_types = {
                "birch": "birch_pollen",
                "grass": "grass_pollen",
                "ragweed": "ragweed_pollen",
                "alder": "alder_pollen",
                "olive": "olive_pollen",
                "mugwort": "mugwort_pollen"
            }

            for key, api_key in pollen_types.items():
                if api_key in hourly and hourly[api_key]:
                    result["pollens"][key] = hourly[api_key][0]

            logger.info(f"✅ Air quality: AQI={result['aqi']}, pollens={result['pollens']}")

        return result

    @staticmethod
    def _calculate_forecast(forecast_data: Dict) -> Dict:
        """
        Вычисляет прогнозные значения на сегодня из почасовых данных
        """
        logger.info(f"🔵 Calculating forecast from data keys: {forecast_data.keys() if forecast_data else 'None'}")

        if not forecast_data:
            logger.warning("⚠️ No forecast data")
            return {}

        if "hourly" not in forecast_data:
            logger.warning("⚠️ No 'hourly' in forecast data")
            return {}

        hourly = forecast_data["hourly"]

        # Получаем все температуры за сегодня
        temps = [t for t in hourly.get("temperature_2m", []) if t is not None]
        humidities = [h for h in hourly.get("relative_humidity_2m", []) if h is not None]
        weather_codes = [w for w in hourly.get("weather_code", []) if w is not None]

        logger.info(f"🌡️ Found {len(temps)} temperature values")
        logger.info(f"💧 Found {len(humidities)} humidity values")
        logger.info(f"☁️ Found {len(weather_codes)} weather codes")

        # Если нет данных, возвращаем пустой объект
        if not temps:
            logger.warning("⚠️ No temperature data available - returning empty forecast")
            return {}

        # Вычисляем статистики
        result = {
            "temperature_max": round(max(temps), 1),
            "temperature_min": round(min(temps), 1),
            "temperature_avg": round(sum(temps) / len(temps), 1),
        }

        if humidities:
            result["humidity_avg"] = round(sum(humidities) / len(humidities), 1)

        if weather_codes:
            from collections import Counter
            code_counts = Counter(weather_codes)
            most_common_code = code_counts.most_common(1)[0][0]
            result["conditions"] = WeatherService._get_weather_description(most_common_code)

        logger.info(f"✅ Calculated forecast: {result}")
        return result

    @staticmethod
    def _get_weather_description(code: int) -> str:
        """Преобразует код погоды WMO в описание"""
        weather_map = {
            0: "clear", 1: "clear", 2: "partly_cloudy", 3: "cloudy",
            45: "foggy", 48: "foggy",
            51: "drizzle", 53: "drizzle", 55: "drizzle",
            61: "rainy", 63: "rainy", 65: "rainy",
            71: "snowy", 73: "snowy", 75: "snowy",
            80: "rainy", 81: "rainy", 82: "rainy",
            95: "stormy", 96: "stormy", 99: "stormy"
        }
        return weather_map.get(code, "unknown")

    @staticmethod
    def _extract_pollen_details(air_data: Dict) -> Dict:
        """Извлекает и структурирует детальные данные о пыльце"""
        if not air_data or "pollens" not in air_data:
            return {
                "types": {},
                "active": [],
                "summary": {
                    "max": None,
                    "dominant": None,
                    "count": 0,
                    "has_pollen": False
                }
            }

        pollens = air_data["pollens"]

        # Фильтруем только активную пыльцу (> 0)
        active_pollens = {
            name: value for name, value in pollens.items()
            if value is not None and value > 0
        }

        # Русские названия для типов пыльцы
        pollen_names_ru = {
            "birch": "Береза",
            "grass": "Злаки",
            "ragweed": "Амброзия",
            "alder": "Ольха",
            "olive": "Олива",
            "mugwort": "Полынь"
        }

        # Форматируем активную пыльцу для отображения
        active_formatted = []
        for name, value in active_pollens.items():
            active_formatted.append({
                "type": name,
                "name_ru": pollen_names_ru.get(name, name),
                "value": value,
                "level": WeatherService._get_pollen_level(value)
            })

        # Сортируем по убыванию значения
        active_formatted.sort(key=lambda x: x["value"], reverse=True)

        # Определяем доминирующий тип
        dominant = active_formatted[0]["type"] if active_formatted else None
        dominant_value = active_formatted[0]["value"] if active_formatted else None

        return {
            "types": pollens,
            "active": active_formatted,
            "summary": {
                "max": max(pollens.values()) if pollens and any(v for v in pollens.values() if v) else None,
                "dominant": dominant,
                "dominant_value": dominant_value,
                "count": len(active_formatted),
                "has_pollen": len(active_formatted) > 0
            }
        }

    @staticmethod
    def _get_pollen_level(value: float) -> str:
        """Определяет уровень опасности пыльцы"""
        if value is None:
            return "нет данных"
        if value > 100:
            return "очень высокий"
        if value > 50:
            return "высокий"
        if value > 20:
            return "средний"
        if value > 0:
            return "низкий"
        return "отсутствует"

    @staticmethod
    async def get_pollen_details(lat: float, lon: float) -> Optional[Dict]:
        """Детальные данные по типам пыльцы"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                air_data = await WeatherService._fetch_air_quality(client, lat, lon)
                return WeatherService._extract_pollen_details(air_data)
            except Exception as e:
                logger.error(f"Failed to get pollen details: {e}")
                return None