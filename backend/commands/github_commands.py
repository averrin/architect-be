import httpx
from firebase_client import get_db

GITHUB_API = "https://api.github.com"
JULES_API = "https://jules.googleapis.com/v1alpha"

async def handle_github_command(uid, cmd_id, data):
    action = data.get("action")
    params = data.get("params", {})

    db = get_db()
    settings_snap = db.document(f"users/{uid}/settings/current").get()
    if not settings_snap.exists:
         raise Exception("Settings not found")

    settings = settings_snap.to_dict()

    if action == "merge_pr":
        owner = settings.get("julesOwner")
        repo = settings.get("julesRepo")
        token = settings.get("julesApiKey")
        pr_number = params.get("number")

        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/merge"
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient() as client:
            resp = await client.put(url, headers=headers)
            return resp.json()

    elif action == "send_jules_message":
        api_key = settings.get("julesGoogleApiKey")
        session_id = params.get("sessionId")
        message = params.get("message")

        url = f"{JULES_API}/sessions/{session_id}:sendMessage"
        headers = {"x-goog-api-key": api_key}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, json={"message": message})
            return resp.json()

    elif action == "delete_jules_session":
         api_key = settings.get("julesGoogleApiKey")
         session_id = params.get("sessionId")
         url = f"{JULES_API}/sessions/{session_id}"
         headers = {"x-goog-api-key": api_key}
         async with httpx.AsyncClient() as client:
             resp = await client.delete(url, headers=headers)
             return {"status": resp.status_code}

    return {"status": "unknown_action"}
