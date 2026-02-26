import httpx
from firebase_client import get_db
from models.jules import JulesSession
from firebase_admin import firestore
from logger import logger

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

async def update_jules_sessions(uid: str):
    logger.debug(f"Updating Jules sessions for {uid}")
    db = get_db()
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        logger.debug(f"No settings for user {uid}")
        return

    user_settings = settings_snap.to_dict()
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
    users = db.collection("users").stream()
    for user in users:
        await update_jules_sessions(user.id)
    logger.info("Jules job completed")
