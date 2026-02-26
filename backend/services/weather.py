import httpx
from firebase_client import get_db
from models.weather import WeatherData, HourlyWeatherData
from utils.weather_codes import get_weather_info
from utils.user_data import get_active_users
from firebase_admin import firestore
from logger import logger
import asyncio

API_URL = "https://api.open-meteo.com/v1/forecast"

async def update_weather(uid: str, settings_data: dict):
    logger.debug(f"Updating weather for {uid}")
    db = get_db()

    # Check if settings provided
    if not settings_data:
        logger.debug(f"No settings provided for user {uid}")
        return

    lat = settings_data.get("location", {}).get("lat")
    lon = settings_data.get("location", {}).get("lon")

    if not lat or not lon:
        # Fallback to top level lat/lon if structure differs
        lat = settings_data.get("lat")
        lon = settings_data.get("lon")

    if not lat or not lon:
        logger.debug(f"No location set for user {uid}")
        return

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "hourly": "temperature_2m,weather_code",
        "timezone": "auto"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch weather for {uid}: {e}")
        return

    # Process data
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})

    forecast_data = {}

    # We need to map daily data
    times = daily.get("time", [])
    codes = daily.get("weather_code", [])
    max_temps = daily.get("temperature_2m_max", [])
    min_temps = daily.get("temperature_2m_min", [])

    for i, date_str in enumerate(times):
        code = codes[i]
        icon, label = get_weather_info(code)

        # Filter hourly for this day
        day_hourly = []
        h_times = hourly.get("time", [])
        h_temps = hourly.get("temperature_2m", [])
        h_codes = hourly.get("weather_code", [])

        for j, h_time in enumerate(h_times):
            if h_time.startswith(date_str):
                h_code = h_codes[j]
                h_icon, h_label = get_weather_info(h_code)
                day_hourly.append(HourlyWeatherData(
                    time=h_time,
                    temp=h_temps[j],
                    weatherCode=h_code,
                    icon=h_icon,
                    label=h_label
                ))

        forecast_data[date_str] = WeatherData(
            date=date_str,
            minTemp=min_temps[i],
            maxTemp=max_temps[i],
            weatherCode=code,
            icon=icon,
            label=label,
            hourly=day_hourly
        ).model_dump()

    # Write to Firestore
    db.document(f"users/{uid}/weather/forecast").set({
        "data": forecast_data,
        "updatedAt": firestore.SERVER_TIMESTAMP
    })
    logger.info(f"Weather updated for {uid}")

async def run_weather_job():
    logger.info("Starting weather job")
    db = get_db()

    # Use get_active_users to find users via settings collection group
    # Run in thread to avoid blocking event loop during Firestore sync calls
    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users to process for weather")

    for uid, settings in users_with_settings:
        await update_weather(uid, settings)

    logger.info("Weather job completed")
