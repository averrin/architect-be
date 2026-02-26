from services.buxfer import buxfer_login
import httpx
from firebase_client import get_db
from utils.user_data import parse_settings

async def handle_buxfer_command(uid, cmd_id, data):
    action = data.get("action")
    params = data.get("params", {})

    db = get_db()
    settings_snap = db.document(f"users/{uid}/settings/current").get()
    if not settings_snap.exists:
        raise Exception("Settings not found")

    settings = parse_settings(settings_snap)
    username = settings.get("buxferEmail")
    password = settings.get("buxferPassword")

    if not username or not password:
        raise Exception("Buxfer credentials not found")

    async with httpx.AsyncClient() as client:
        token = await buxfer_login(client, username, password)

        if action == "add_transaction":
             url = "https://www.buxfer.com/api/transaction_add"
             params["token"] = token
             resp = await client.post(url, data=params)
             return resp.json()

        elif action == "edit_transaction":
             url = "https://www.buxfer.com/api/transaction_edit"
             params["token"] = token
             resp = await client.post(url, data=params)
             return resp.json()

    return {"status": "unknown_action"}
