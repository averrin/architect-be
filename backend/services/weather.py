import httpx
from firebase_client import get_db
from models.weather import WeatherData, HourlyWeatherData
from utils.weather_codes import get_weather_info
from firebase_admin import firestore

API_URL = "https://api.open-meteo.com/v1/forecast"

async def update_weather(uid: str):
    db = get_db()
    # Read settings
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        # print(f"No settings for user {uid}")
        return

    settings_data = settings_snap.to_dict()
    lat = settings_data.get("location", {}).get("lat")
    lon = settings_data.get("location", {}).get("lon")

    if not lat or not lon:
        # Fallback to top level lat/lon if structure differs
        lat = settings_data.get("lat")
        lon = settings_data.get("lon")

    if not lat or not lon:
        # print(f"No location set for user {uid}")
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
        print(f"Failed to fetch weather for {uid}: {e}")
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
    print(f"Weather updated for {uid}")

async def run_weather_job():
    db = get_db()
    users = db.collection("users").stream()
    for user in users:
        await update_weather(user.id)
