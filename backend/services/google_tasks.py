import httpx

TASKS_API = "https://tasks.googleapis.com/tasks/v1"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

async def get_access_token(client_id, client_secret, refresh_token):
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_ENDPOINT, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        })
        resp.raise_for_status()
        return resp.json()["access_token"]

class GoogleTasksClient:
    def __init__(self, access_token):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"}

    async def create_task(self, task_list, title, notes=None, due=None):
        url = f"{TASKS_API}/lists/{task_list}/tasks"
        body = {
            "title": title,
            "notes": notes,
            "due": due
        }
        async with httpx.AsyncClient(headers=self.headers) as client:
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            return resp.json()
