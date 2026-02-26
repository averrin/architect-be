import httpx
from firebase_client import get_db
from models.jules import JulesSession
from firebase_admin import firestore
from logger import logger
from utils.user_data import get_active_users
import asyncio

JULES_API = "https://jules.googleapis.com/v1alpha"

async def fetch_jules_sessions(api_key):
    url = f"{JULES_API}/sessions"
    headers = {"x-goog-api-key": api_key}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.debug(f"Jules API returned {resp.status_code}")
                return []
            return resp.json().get("sessions", [])
    except Exception as e:
        logger.error(f"Jules fetch error: {e}")
        return []

async def update_jules_sessions(uid: str, user_settings: dict):
    logger.debug(f"Updating Jules sessions for {uid}")
    db = get_db()

    if not user_settings:
        logger.debug(f"No settings for user {uid}")
        return

    api_key = user_settings.get("julesGoogleApiKey")

    if not api_key:
        logger.debug(f"No Jules API key for user {uid}")
        return

    sessions_data = await fetch_jules_sessions(api_key)

    sessions = []
    for s in sessions_data:
        sessions.append(JulesSession(
            name=s.get("name", ""),
            id=s.get("name", "").split("/")[-1] if "name" in s else "",
            title=s.get("title", ""),
            state=s.get("state", ""),
            url=s.get("url", ""),
            createTime=s.get("createTime", ""),
            updateTime=s.get("updateTime", ""),
            githubMetadata=s.get("githubMetadata")
        ).model_dump())

    if sessions:
        db.document(f"users/{uid}/jules/sessions").set({
            "sessions": sessions,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Jules sessions updated for {uid}")

async def run_jules_job():
    logger.info("Starting Jules job")
    db = get_db()

    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users to process for Jules")

    for uid, settings_data in users_with_settings:
        await update_jules_sessions(uid, settings_data)

    logger.info("Jules job completed")
