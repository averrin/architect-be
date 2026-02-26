from services.gemini import list_models
from firebase_client import get_db
from firebase_admin import firestore
from logger import logger
from utils.user_data import get_active_users
import asyncio

async def sync_models(uid: str, settings_data: dict):
    logger.debug(f"Syncing models for {uid}")
    db = get_db()

    if not settings_data:
        logger.debug(f"No settings for user {uid}")
        return

    api_key = settings_data.get("apiKey")
    if not api_key:
        logger.debug(f"No API key for user {uid}")
        return

    try:
        models = await list_models(api_key)

        gen_models = []
        image_models = []

        for m in models:
            methods = m.supported_generation_methods
            if "generateContent" in methods:
                gen_models.append(m.name)
            if "generateImage" in methods: # Assuming this method name for image gen models
                image_models.append(m.name)

        db.document(f"users/{uid}/ai/models").set({
            "generative": gen_models,
            "image": image_models,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Models synced for {uid}")
    except Exception as e:
        logger.error(f"Model sync error for {uid}: {e}")

async def run_models_sync_job():
    logger.info("Starting models sync job")
    db = get_db()

    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users to process for models sync")

    for uid, settings_data in users_with_settings:
        await sync_models(uid, settings_data)

    logger.info("Models sync job completed")
