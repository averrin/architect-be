import httpx
from firebase_client import get_db
from models.github import WatchedRunData
from firebase_admin import firestore
import time
from datetime import datetime
from logger import logger

GITHUB_API = "https://api.github.com"

async def fetch_workflow_runs(owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params={"per_page": 10})
            resp.raise_for_status()
            return resp.json().get("workflow_runs", [])
    except Exception as e:
        logger.error(f"GitHub fetch error: {e}")
        return []

async def update_github_watcher(uid: str):
    logger.debug(f"Updating GitHub watcher for {uid}")
    db = get_db()
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        logger.debug(f"No settings for user {uid}")
        return

    user_settings = settings_snap.to_dict()
    owner = user_settings.get("julesOwner")
    repo = user_settings.get("julesRepo")
    token = user_settings.get("julesApiKey")

    if not owner or not repo or not token:
        logger.debug(f"No GitHub watcher settings for user {uid}")
        return

    runs = await fetch_workflow_runs(owner, repo, token)

    watched_runs = {}
    current_time = int(time.time() * 1000)

    for run in runs:
        run_id = str(run["id"])
        status = run["status"]
        conclusion = run["conclusion"]

        start_time = 0
        try:
             dt = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
             start_time = int(dt.timestamp() * 1000)
        except:
             pass

        watched_runs[run_id] = WatchedRunData(
            runId=run["id"],
            name=run["name"],
            headBranch=run["head_branch"],
            headCommitMessage=run["head_commit"]["message"] if run.get("head_commit") else None,
            status=status,
            conclusion=conclusion,
            estimatedDuration=0,
            startTime=start_time,
            lastChecked=current_time,
            progress=0.0,
            artifactUrl=None,
            htmlUrl=run["html_url"],
            owner=owner,
            repo=repo
        ).model_dump()

    if watched_runs:
        db.document(f"users/{uid}/github/watchedRuns").set({
            "runs": watched_runs,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"GitHub runs updated for {uid}")

async def run_github_job():
    logger.info("Starting GitHub job")
    db = get_db()
    users = db.collection("users").stream()
    for user in users:
        await update_github_watcher(user.id)
    logger.info("GitHub job completed")
