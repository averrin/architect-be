import httpx
from firebase_client import get_db
from models.github import WatchedRunData
from firebase_admin import firestore
import time
from datetime import datetime
from logger import logger
from utils.user_data import get_active_users
from utils.fcm import get_fcm_token, send_fcm_message
from config import get_settings
import asyncio

GITHUB_API = "https://api.github.com"
settings = get_settings()

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

async def fetch_artifact_url(owner, repo, token, run_id):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            artifacts = resp.json().get("artifacts", [])
            if artifacts:
                # Get the first artifact's archive download URL
                download_url = artifacts[0]["archive_download_url"]
                # Follow redirect to get the actual storage URL
                resp = await client.get(download_url, headers=headers, follow_redirects=True)
                # If we followed redirects, the final URL is in resp.url
                # However, for private repos, this might need authentication.
                # GitHub Actions artifacts usually expire and are zipped.
                # The archive_download_url redirects to a blob storage URL which is temporary.
                return str(resp.url)
            return None
    except Exception as e:
        logger.error(f"GitHub artifact fetch error: {e}")
        return None

async def update_github_watcher(uid: str, user_settings: dict):
    # logger.debug(f"Updating GitHub watcher for {uid}")
    db = get_db()

    if not user_settings:
        logger.debug(f"No settings for user {uid}")
        return

    owner = user_settings.get("julesOwner")
    repo = user_settings.get("julesRepo")
    token = user_settings.get("julesApiKey")

    if not owner or not repo or not token:
        logger.debug(f"No GitHub watcher settings for user {uid}")
        return

    # Check existing state to determine polling frequency
    watched_runs_ref = db.document(f"users/{uid}/github/watchedRuns")
    watched_runs_snap = watched_runs_ref.get()

    old_runs = {}
    last_updated = 0
    has_active_runs = False

    if watched_runs_snap.exists:
        data = watched_runs_snap.to_dict()
        old_runs = data.get("runs", {})
        # Check if 'updatedAt' exists and is not None
        if data.get("updatedAt"):
             last_updated = data.get("updatedAt").timestamp()

        for run_id, run_data in old_runs.items():
            if run_data.get("status") in ["queued", "in_progress"]:
                has_active_runs = True
                break

    current_time_ts = time.time()

    # Determine if we should skip this poll
    # If no active runs, poll slowly
    if not has_active_runs:
        time_diff = current_time_ts - last_updated
        if time_diff < (settings.GITHUB_WATCHER_SLOW_INTERVAL_MINUTES * 60):
            # logger.debug(f"Skipping GitHub poll for {uid} (slow mode)")
            return

    runs = await fetch_workflow_runs(owner, repo, token)

    # If no runs found, and we didn't have active runs, we are done
    if not runs and not has_active_runs:
         return

    watched_runs = {}
    current_time_ms = int(current_time_ts * 1000)

    fcm_token = None

    for run in runs:
        run_id = str(run["id"])
        status = run["status"]
        conclusion = run["conclusion"]

        old_run = old_runs.get(run_id)

        # State transition detection
        if old_run:
            old_status = old_run.get("status")
            # old_conclusion = old_run.get("conclusion")

            # Queued -> In Progress
            if old_status == "queued" and status == "in_progress":
                if not fcm_token: fcm_token = get_fcm_token(uid, db)
                send_fcm_message(fcm_token, {
                    "type": "github_run",
                    "status": "started",
                    "runId": run_id,
                    "repo": repo,
                    "name": run["name"]
                }, notification={
                    "title": f"Run Started: {run['name']}",
                    "body": f"GitHub Action started on {repo}"
                })

            # Any -> Completed
            if old_status != "completed" and status == "completed":
                artifact_url = None
                # Fetch artifact if successful or we just want artifacts for any completion
                if conclusion == "success":
                     artifact_url = await fetch_artifact_url(owner, repo, token, run_id)

                if not fcm_token: fcm_token = get_fcm_token(uid, db)

                msg_data = {
                    "type": "github_run",
                    "status": "completed",
                    "conclusion": conclusion,
                    "runId": run_id,
                    "repo": repo,
                    "name": run["name"]
                }
                if artifact_url:
                    msg_data["artifactUrl"] = artifact_url

                send_fcm_message(fcm_token, msg_data, notification={
                    "title": f"Run {conclusion.title()}: {run['name']}",
                    "body": f"GitHub Action completed on {repo}"
                })

                # We need to store the artifact URL in the new state so we don't lose it
                # But wait, we construct the new state below.

        start_time = 0
        try:
             dt = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
             start_time = int(dt.timestamp() * 1000)
        except:
             pass

        # Preserve artifact URL if we already had it and it's not being re-fetched this cycle
        # Or if we just fetched it above (we didn't store it in a variable accessible here easily yet)

        # Re-fetch artifact URL if completed and we don't have it?
        # For simplicity, if it's completed now, let's try to get it if we don't have it.
        artifact_url = old_run.get("artifactUrl") if old_run else None

        # If it just completed, we might have fetched it in the transition block?
        # Let's refine the logic.

        if status == "completed":
            # If it just transitioned, we should fetch.
            # If it was already completed but we don't have URL, maybe fetch? (Might be expensive to do every time)
            # Let's only fetch on transition to completed.
            if old_run and old_run.get("status") != "completed":
                 # We already fetched in the block above, need to duplicate logic or restructure?
                 # Let's restructure slightly by moving fetch here.
                 if conclusion == "success":
                     artifact_url = await fetch_artifact_url(owner, repo, token, run_id)
            elif not old_run:
                 # New run that is already completed (missed the transition)
                 if conclusion == "success":
                     artifact_url = await fetch_artifact_url(owner, repo, token, run_id)

        watched_runs[run_id] = WatchedRunData(
            runId=run["id"],
            name=run["name"],
            headBranch=run["head_branch"],
            headCommitMessage=run["head_commit"]["message"] if run.get("head_commit") else None,
            status=status,
            conclusion=conclusion,
            estimatedDuration=0,
            startTime=start_time,
            lastChecked=current_time_ms,
            progress=0.0,
            artifactUrl=artifact_url,
            htmlUrl=run["html_url"],
            owner=owner,
            repo=repo
        ).model_dump()

    if watched_runs:
        watched_runs_ref.set({
            "runs": watched_runs,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"GitHub runs updated for {uid}")

async def run_github_job():
    logger.info("Starting GitHub job")
    db = get_db()

    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users to process for GitHub")

    for uid, settings_data in users_with_settings:
        await update_github_watcher(uid, settings_data)

    logger.info("GitHub job completed")
