import httpx
from firebase_client import get_db
from models.jules import JulesSession
from firebase_admin import firestore

JULES_API = "https://jules.googleapis.com/v1alpha"

async def fetch_jules_sessions(api_key):
    url = f"{JULES_API}/sessions"
    headers = {"x-goog-api-key": api_key}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                return []
            return resp.json().get("sessions", [])
    except Exception as e:
        print(f"Jules fetch error: {e}")
        return []

async def update_jules_sessions(uid: str):
    db = get_db()
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        return

    user_settings = settings_snap.to_dict()
    api_key = user_settings.get("julesGoogleApiKey")

    if not api_key:
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
        print(f"Jules sessions updated for {uid}")

async def run_jules_job():
    db = get_db()
    users = db.collection("users").stream()
    for user in users:
        await update_jules_sessions(user.id)
