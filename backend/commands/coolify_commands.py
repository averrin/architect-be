from logger import logger
from services.coolify import control_coolify_application, update_coolify_applications
from utils.user_data import parse_settings
from firebase_client import get_db
from config import get_settings
import asyncio

settings = get_settings()

async def handle_coolify_command(uid: str, cmd_id: str, data: dict):
    action = data.get("action")
    db = get_db()

    settings_doc = await asyncio.to_thread(
        lambda: db.document(f"users/{uid}/settings/current").get()
    )
    user_settings = parse_settings(settings_doc)
    host = user_settings.get("coolifyHost") or settings.COOLIFY_URL
    token = user_settings.get("coolifyToken") or settings.COOLIFY_API_TOKEN

    if not host or not token:
        raise ValueError("Coolify host/token not configured")

    if action in ("start", "stop", "restart"):
        app_uuid = data.get("appUuid")
        if not app_uuid:
            raise ValueError("appUuid is required")
        result = await control_coolify_application(host, token, app_uuid, action)
        logger.info(f"Coolify {action} triggered for app {app_uuid} by {uid}: {result}")
        await update_coolify_applications(uid, host, token)
        return {"status": action, "result": result}

    raise ValueError(f"Unknown coolify action: {action}")
