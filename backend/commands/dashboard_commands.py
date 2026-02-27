from logger import logger
from services.dashboard import update_dashboard_discovery
from utils.user_data import parse_settings
from firebase_client import get_db
import asyncio


async def handle_dashboard_command(uid: str, cmd_id: str, data: dict):
    action = data.get("action")

    if action == "refresh":
        db = get_db()
        settings_doc = await asyncio.to_thread(
            lambda: db.document(f"users/{uid}/settings/current").get()
        )
        user_settings = parse_settings(settings_doc)
        await update_dashboard_discovery(uid, user_settings)
        logger.info(f"Dashboard refresh triggered by command for {uid}")
        return {"status": "refreshed"}

    raise ValueError(f"Unknown dashboard action: {action}")
