import httpx
from firebase_client import get_db
from models.jules import JulesSession
from firebase_admin import firestore
from logger import logger
from utils.user_data import get_active_users
from utils.fcm import get_fcm_token, send_fcm_message
from config import get_settings
import asyncio
import time

JULES_API = "https://jules.googleapis.com/v1alpha"
settings = get_settings()

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
    # logger.debug(f"Updating Jules sessions for {uid}")
    db = get_db()

    if not user_settings:
        logger.debug(f"No settings for user {uid}")
        return

    api_key = user_settings.get("julesGoogleApiKey")

    if not api_key:
        logger.debug(f"No Jules API key for user {uid}")
        return

    # Check existing state to determine polling frequency
    sessions_ref = db.document(f"users/{uid}/jules/sessions")
    sessions_snap = sessions_ref.get()

    old_sessions = {}
    last_updated = 0
    has_active_sessions = False

    if sessions_snap.exists:
        data = sessions_snap.to_dict()
        # The stored format is a list called "sessions", let's index by ID for easier comparison
        stored_list = data.get("sessions", [])
        if stored_list:
            for s in stored_list:
                old_sessions[s.get("id")] = s
                # Assuming 'STATE_ACTIVE' or similar, but looking at proto, states are like 'STATE_UNSPECIFIED', 'CREATING', 'ACTIVE', 'DELETING'
                if s.get("state") in ["CREATING", "ACTIVE", "INITIALIZING"]:
                    has_active_sessions = True

        if data.get("updatedAt"):
             last_updated = data.get("updatedAt").timestamp()

    current_time_ts = time.time()

    # Determine if we should skip this poll
    if not has_active_sessions:
        time_diff = current_time_ts - last_updated
        if time_diff < (settings.JULES_SLOW_INTERVAL_MINUTES * 60):
            # logger.debug(f"Skipping Jules poll for {uid} (slow mode)")
            return

    sessions_data = await fetch_jules_sessions(api_key)

    if not sessions_data and not has_active_sessions:
        return

    sessions = []
    fcm_token = None

    for s in sessions_data:
        session_id = s.get("name", "").split("/")[-1] if "name" in s else ""
        current_state = s.get("state", "")

        new_session = JulesSession(
            name=s.get("name", ""),
            id=session_id,
            title=s.get("title", ""),
            state=current_state,
            url=s.get("url", ""),
            createTime=s.get("createTime", ""),
            updateTime=s.get("updateTime", ""),
            githubMetadata=s.get("githubMetadata")
        ).model_dump()

        sessions.append(new_session)

        # Check for state changes
        old_session = old_sessions.get(session_id)

        if old_session:
            old_state = old_session.get("state")
            if old_state != current_state:
                if not fcm_token: fcm_token = get_fcm_token(uid, db)

                # Notify on interesting state changes
                if current_state == "ACTIVE":
                     send_fcm_message(fcm_token, {
                        "type": "jules_session",
                        "status": "active",
                        "sessionId": session_id,
                        "title": s.get("title", "")
                    }, notification={
                        "title": "Jules Session Active",
                        "body": f"Session '{s.get('title', 'Untitled')}' is now active."
                    })
        elif not old_session:
            # New session found
            if not fcm_token: fcm_token = get_fcm_token(uid, db)
            send_fcm_message(fcm_token, {
                "type": "jules_session",
                "status": "created",
                "sessionId": session_id,
                "title": s.get("title", "")
            }, notification={
                "title": "New Jules Session",
                "body": f"Session '{s.get('title', 'Untitled')}' created."
            })


    if sessions:
        sessions_ref.set({
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
