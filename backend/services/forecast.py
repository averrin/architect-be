from services.gemini import generate_content, configure_genai
from firebase_client import get_db
from firebase_admin import firestore
from datetime import datetime
import asyncio

async def generate_day_forecast(uid: str):
    db = get_db()
    # Read settings
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        return

    settings_data = settings_snap.to_dict()
    api_key = settings_data.get("apiKey")
    if not api_key:
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
        print(f"Forecast generated for {uid}")
    except Exception as e:
        print(f"Forecast error for {uid}: {e}")

async def run_forecast_job():
    db = get_db()
    users = db.collection("users").stream()
    for user in users:
        await generate_day_forecast(user.id)
