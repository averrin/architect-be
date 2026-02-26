from services.gemini import generate_content, configure_genai
from firebase_client import get_db
from firebase_admin import firestore
from datetime import datetime
import asyncio
from logger import logger

async def generate_day_forecast(uid: str):
    logger.debug(f"Generating forecast for {uid}")
    db = get_db()
    # Read settings
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        logger.debug(f"No settings for user {uid}")
        return

    settings_data = settings_snap.to_dict()
    api_key = settings_data.get("apiKey")
    if not api_key:
        logger.debug(f"No API key for user {uid}")
        return

    configure_genai(api_key)

    context = f"Today is {datetime.now().strftime('%A, %B %d, %Y')}."

    prompt = f"{context}\nGenerate a personalized daily forecast and advice."

    try:
        response = await generate_content(api_key, "gemini-pro", prompt)
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
    users = list(db.collection("users").stream())
    logger.info(f"Found {len(users)} users to process for forecast")
    for user in users:
        await generate_day_forecast(user.id)
    logger.info("Forecast job completed")
