from services.gemini import generate_content, configure_genai
from firebase_client import get_db
from firebase_admin import firestore
from datetime import datetime
import asyncio
from logger import logger
from utils.user_data import get_active_users

async def generate_day_forecast(uid: str, settings_data: dict):
    logger.debug(f"Generating forecast for {uid}")
    db = get_db()

    if not settings_data:
        logger.debug(f"No settings for user {uid}")
        return

    model = settings_data.get("selectedModel")
    api_key = settings_data.get("apiKey")
    if not api_key:
        logger.debug(f"No API key for user {uid}")
        return

    configure_genai(api_key)

    context = f"Today is {datetime.now().strftime('%A, %B %d, %Y')}."

    prompt = f"{context}\nGenerate a personalized daily forecast and advice."

    try:
        response = await generate_content(api_key, model, prompt)
        text = response.text

        db.document(f"users/{uid}/forecast/today").set({
            "text": text,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Forecast generated for {uid}")
    except Exception as e:
        logger.error(f"Forecast error for {uid}: {e}")

async def run_forecast_job():
    logger.info("Starting forecast job")
    db = get_db()

    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users to process for forecast")

    for uid, settings_data in users_with_settings:
        await generate_day_forecast(uid, settings_data)

    logger.info("Forecast job completed")
