from services.google_tasks import get_access_token, GoogleTasksClient
from firebase_client import get_db
from config import get_settings

async def handle_gtasks_command(uid, cmd_id, data):
    action = data.get("action")
    params = data.get("params", {})

    db = get_db()

    settings_snap = db.document(f"users/{uid}/settings/current").get()
    if not settings_snap.exists:
        raise Exception("Settings not found")

    settings = settings_snap.to_dict()
    refresh_token = settings.get("googleTasksRefreshToken")

    if not refresh_token:
         raise Exception("Google Tasks Refresh Token not found")

    app_settings = get_settings()
    client_id = app_settings.GOOGLE_CLIENT_ID
    client_secret = app_settings.GOOGLE_CLIENT_SECRET

    if not client_id or not client_secret:
         raise Exception("Google Client ID/Secret not configured in backend")

    access_token = await get_access_token(client_id, client_secret, refresh_token)
    client = GoogleTasksClient(access_token)

    if action == "create_task":
        task_list = params.get("listId", "@default")
        title = params.get("title")
        notes = params.get("notes")
        due = params.get("due")

        result = await client.create_task(task_list, title, notes, due)
        return result

    return {"status": "unknown_action"}
