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

async def fetch_workflow_runs(client, owner, repo, token):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        resp = await client.get(url, headers=headers, params={"per_page": 10})
        resp.raise_for_status()
        runs = resp.json().get("workflow_runs", [])
        for r in runs:
            r["_owner"] = owner
            r["_repo"] = repo
        return runs
    except Exception as e:
        logger.error(f"GitHub fetch error for {owner}/{repo}: {e}")
        return []

async def fetch_artifact_url(client, owner, repo, token, run_id):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    try:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        artifacts = resp.json().get("artifacts", [])
        if artifacts:
            # Get the first artifact's archive download URL
            download_url = artifacts[0]["archive_download_url"]
            # Stream the request to avoid downloading the body, but follow redirects to get final URL
            # Note: httpx client.stream context manager automatically closes the response
            try:
                async with client.stream("GET", download_url, headers=headers, follow_redirects=True) as response:
                    return str(response.url)
            except Exception as e:
                logger.error(f"Error streaming artifact URL for run {run_id}: {e}")
                return None
        return None
    except Exception as e:
        logger.error(f"GitHub artifact fetch error for run {run_id}: {e}")
        return None

async def update_github_watcher(uid: str, user_settings: dict):
    # logger.debug(f"Updating GitHub watcher for {uid}")
    db = get_db()

    if not user_settings:
        logger.debug(f"No settings for user {uid}")
        return

    token = user_settings.get("julesApiKey")

    if not token:
        logger.debug(f"No GitHub watcher settings for user {uid}")
        return

    # Fetch active repos from Jules sessions
    sessions_ref = db.document(f"users/{uid}/jules/sessions")
    sessions_snap = sessions_ref.get()

    unique_repos = set()

    if sessions_snap.exists:
        sessions_data = sessions_snap.to_dict().get("sessions", [])
        for session in sessions_data:
            gh_meta = session.get("githubMetadata")
            if gh_meta and gh_meta.get("owner") and gh_meta.get("repo"):
                unique_repos.add((gh_meta["owner"], gh_meta["repo"]))

    # Fallback to settings if no sessions found (or if user wants specific repo watched)
    manual_owner = user_settings.get("julesOwner")
    manual_repo = user_settings.get("julesRepo")
    if manual_owner and manual_repo:
        unique_repos.add((manual_owner, manual_repo))

    if not unique_repos:
        # logger.debug(f"No repos to watch for user {uid}")
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
        if data.get("updatedAt"):
             last_updated = data.get("updatedAt").timestamp()

        for run_id, run_data in old_runs.items():
            if run_data.get("status") in ["queued", "in_progress"]:
                has_active_runs = True
                break

    current_time_ts = time.time()

    # Determine if we should skip this poll
    if not has_active_runs:
        time_diff = current_time_ts - last_updated
        if time_diff < (settings.GITHUB_WATCHER_SLOW_INTERVAL_MINUTES * 60):
            logger.debug(f"Skipping GitHub poll for {uid} (slow mode, last active {int(time_diff)}s ago)")
            return

    logger.info(f"Checking GitHub runs for {uid} on {len(unique_repos)} repos")

    # Aggregate runs from all repos concurrently
    all_runs = []

    async with httpx.AsyncClient() as client:
        tasks = [fetch_workflow_runs(client, owner, repo, token) for owner, repo in unique_repos]
        results = await asyncio.gather(*tasks)
        for res in results:
            all_runs.extend(res)

        if not all_runs and not has_active_runs:
            logger.debug(f"No active runs found for {uid}")
            return

        watched_runs = {}
        current_time_ms = int(current_time_ts * 1000)
        fcm_token = None

        notifications_sent = 0

        for run in all_runs:
            run_id = str(run["id"])
            status = run["status"]
            conclusion = run["conclusion"]
            owner = run.get("_owner")
            repo = run.get("_repo")

            old_run = old_runs.get(run_id)

            # Determine if we need to notify
            notify_start = False
            notify_complete = False

            if old_run:
                old_status = old_run.get("status")
                if old_status == "queued" and status == "in_progress":
                    notify_start = True
                if old_status != "completed" and status == "completed":
                    notify_complete = True
            else:
                # New run detected
                if status == "in_progress":
                    notify_start = True
                if status == "completed":
                    notify_complete = True

            head_commit = run.get("head_commit")
            commit_message = head_commit["message"] if head_commit else "No commit message"
            head_branch = run.get("head_branch")

            if notify_start:
                if not fcm_token: fcm_token = get_fcm_token(uid, db)
                logger.info(f"GitHub run {run_id} started on {repo}. Sending notification.")
                send_fcm_message(fcm_token, {
                    "type": "github_run",
                    "status": "started",
                    "runId": run_id,
                    "repo": repo,
                    "name": run["name"],
                    "headBranch": head_branch,
                    "headCommitMessage": commit_message
                }, notification={
                    "title": f"Run Started: {run['name']}",
                    "body": f"Repo: {repo}\nBranch: {head_branch}\nCommit: {commit_message}"
                })
                notifications_sent += 1

            artifact_url = old_run.get("artifactUrl") if old_run else None

            if notify_complete:
                logger.info(f"GitHub run {run_id} completed on {repo} ({conclusion}). Sending notification.")
                # Fetch artifact URL if successful
                if conclusion == "success":
                    logger.debug(f"Fetching artifact URL for run {run_id}")
                    artifact_url = await fetch_artifact_url(client, owner, repo, token, run_id)
                    if artifact_url:
                        logger.debug(f"Found artifact URL: {artifact_url}")
                    else:
                        logger.debug(f"No artifact URL found for {run_id}")

                if not fcm_token: fcm_token = get_fcm_token(uid, db)

                msg_data = {
                    "type": "github_run",
                    "status": "completed",
                    "conclusion": conclusion,
                    "runId": run_id,
                    "repo": repo,
                    "name": run["name"],
                    "headBranch": head_branch,
                    "headCommitMessage": commit_message
                }
                if artifact_url:
                    msg_data["artifactUrl"] = artifact_url

                send_fcm_message(fcm_token, msg_data, notification={
                    "title": f"Run {conclusion.title()}: {run['name']}",
                    "body": f"GitHub Action completed on {repo}"
                })
                notifications_sent += 1

            start_time = 0
            try:
                dt = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
                start_time = int(dt.timestamp() * 1000)
            except:
                pass

            watched_runs[run_id] = WatchedRunData(
                runId=run["id"],
                name=run["name"],
                headBranch=head_branch,
                headCommitMessage=commit_message if head_commit else None,
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
        logger.info(f"GitHub runs updated for {uid}: {len(watched_runs)} runs tracked (sent {notifications_sent} notifications)")

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
