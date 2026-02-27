import httpx
from firebase_client import get_db
from models.jules import JulesSession
from models.github import WatchedRunData
from models.dashboard import DashboardData, JointSessionModel
from firebase_admin import firestore
from logger import logger
from utils.user_data import get_active_users
from utils.fcm import get_fcm_token, send_fcm_message
from config import get_settings
import asyncio
import time
from datetime import datetime

settings = get_settings()

JULES_API = "https://jules.googleapis.com/v1alpha"
GITHUB_API = "https://api.github.com"

# --- Fetch Functions (Reused/Refactored) ---

async def fetch_jules_sessions(api_key):
    url = f"{JULES_API}/sessions"
    headers = {"x-goog-api-key": api_key}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.debug(f"Jules API returned {resp.status_code} for fetch_jules_sessions")
                return []
            return resp.json().get("sessions", [])
    except Exception as e:
        logger.error(f"Jules fetch error: {e}")
        return []

async def fetch_workflow_runs(client, owner, repo, token, branch=None):
    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}
    params = {"per_page": 20} # Fetch more to cover recent history
    if branch:
        params["branch"] = branch

    try:
        resp = await client.get(url, headers=headers, params=params)
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
            download_url = artifacts[0]["archive_download_url"]
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

# --- Main Logic ---

async def update_dashboard_discovery(uid: str, user_settings: dict):
    # Discovery Phase: Full Refresh
    try:
        db = get_db()

        if not user_settings:
            logger.debug(f"No settings for user {uid}")
            return

        jules_api_key = user_settings.get("julesGoogleApiKey")
        github_token = user_settings.get("julesApiKey")

        if not jules_api_key or not github_token:
            logger.debug(f"Missing API keys for user {uid}")
            return

        # 1. Fetch Jules Sessions
        raw_sessions = await fetch_jules_sessions(jules_api_key)
        logger.debug(f"Fetched {len(raw_sessions)} Jules sessions for {uid}")

        try:
            raw_sessions.sort(key=lambda x: x.get("createTime", ""), reverse=True)
        except Exception:
            pass

        top_sessions = raw_sessions[:10]

        # 2. Identify Unique Repos from Top Sessions
        unique_repos = set()
        for s in top_sessions:
            meta = s.get("githubMetadata", {})
            if meta and meta.get("owner") and meta.get("repo"):
                unique_repos.add((meta["owner"], meta["repo"]))

        # Also include manual repo from settings if present
        manual_owner = user_settings.get("julesOwner")
        manual_repo = user_settings.get("julesRepo")
        if manual_owner and manual_repo:
            unique_repos.add((manual_owner, manual_repo))

        # 3. Fetch GitHub Runs for these Repos
        all_runs = []
        async with httpx.AsyncClient() as client:
            tasks = []
            for owner, repo in unique_repos:
                tasks.append(fetch_workflow_runs(client, owner, repo, github_token))

            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"Error fetching runs for one repo: {res}")
                elif res:
                    all_runs.extend(res)

        logger.debug(f"Fetched {len(all_runs)} GitHub runs for {uid}")

        # 4. Construct Joint Models
        joint_sessions = []

        for s in top_sessions:
            session_id = s.get("name", "").split("/")[-1]
            session_model = JulesSession(
                name=s.get("name", ""),
                id=session_id,
                title=s.get("title", ""),
                state=s.get("state", ""),
                url=s.get("url", ""),
                createTime=s.get("createTime", ""),
                updateTime=s.get("updateTime", ""),
                githubMetadata=s.get("githubMetadata")
            )

            matched_run = None
            gh_meta = s.get("githubMetadata")

            if gh_meta:
                target_owner = gh_meta.get("owner")
                target_repo = gh_meta.get("repo")
                target_branch = gh_meta.get("branch")
                target_pr = gh_meta.get("pullRequestNumber")

                session_start_time = 0
                try:
                    dt = datetime.fromisoformat(s.get("createTime", "").replace("Z", "+00:00"))
                    session_start_time = int(dt.timestamp() * 1000)
                except:
                    pass

                # Filter runs for this repo first
                repo_runs = [r for r in all_runs if r.get("_owner") == target_owner and r.get("_repo") == target_repo]

                # Priority 1: Match by PR number
                if target_pr:
                    for r in repo_runs:
                        prs = r.get("pull_requests", [])
                        if any(pr.get("number") == target_pr for pr in prs):
                            matched_run = _create_watched_run_data(r)
                            break

                # Priority 2: Match by Branch + Time Constraint (fallback)
                if not matched_run and target_branch:
                    candidates = []
                    for r in repo_runs:
                        if r.get("head_branch") == target_branch:
                            run_created_at = 0
                            try:
                                dt = datetime.fromisoformat(r.get("created_at", "").replace("Z", "+00:00"))
                                run_created_at = int(dt.timestamp() * 1000)
                            except:
                                pass

                            # Allow runs created up to 60s before session start
                            if run_created_at >= session_start_time - 60000:
                                candidates.append(r)

                    if candidates:
                        # Sort by created_at desc to find latest
                        candidates.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                        matched_run = _create_watched_run_data(candidates[0])

            joint_sessions.append(JointSessionModel(session=session_model, run=matched_run))

        # 5. Construct Master Runs List
        master_runs_data = []

        master_candidates = [r for r in all_runs if r.get("head_branch") in ["master", "main"]]
        master_candidates.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        top_master_runs = master_candidates[:5]

        for r in top_master_runs:
            master_runs_data.append(_create_watched_run_data(r))

        # 6. Save Dashboard Data
        dashboard_data = DashboardData(
            jointSessions=joint_sessions,
            masterRuns=master_runs_data,
            updatedAt=int(time.time() * 1000)
        )

        dashboard_ref = db.document(f"users/{uid}/dashboard/data")
        dashboard_ref.set(dashboard_data.model_dump())
        logger.info(f"Dashboard discovery updated for {uid}")

    except Exception as e:
        logger.error(f"Error in update_dashboard_discovery for {uid}: {e}")


async def update_dashboard_status(uid: str, user_settings: dict):
    # Status Update Phase: Check Active Items
    try:
        db = get_db()

        dashboard_ref = db.document(f"users/{uid}/dashboard/data")
        doc = dashboard_ref.get()

        if not doc.exists:
            return

        data = doc.to_dict()

        joint_sessions = data.get("jointSessions", [])
        master_runs = data.get("masterRuns", [])

        active_sessions_indices = []
        active_runs_indices = []

        # Identify Active Sessions
        for idx, item in enumerate(joint_sessions):
            s = item.get("session", {})
            if s.get("state") in ["CREATING", "ACTIVE", "INITIALIZING"]:
                active_sessions_indices.append(idx)

            r = item.get("run")
            if r and r.get("status") in ["queued", "in_progress"]:
                active_runs_indices.append(("jointSessions", idx, r.get("runId"), r.get("owner"), r.get("repo")))

        # Identify Active Master Runs
        for idx, r in enumerate(master_runs):
            if r.get("status") in ["queued", "in_progress"]:
                active_runs_indices.append(("masterRuns", idx, r.get("runId"), r.get("owner"), r.get("repo")))

        if not active_sessions_indices and not active_runs_indices:
            return

        jules_api_key = user_settings.get("julesGoogleApiKey")
        github_token = user_settings.get("julesApiKey")

        updated = False
        fcm_token = None

        # Refetch Active Sessions
        if active_sessions_indices:
            fresh_sessions_list = await fetch_jules_sessions(jules_api_key)
            fresh_map = {s.get("name", "").split("/")[-1]: s for s in fresh_sessions_list}

            for idx in active_sessions_indices:
                item = joint_sessions[idx]
                s_old = item["session"]
                sid = s_old["id"]

                if sid in fresh_map:
                    s_new_raw = fresh_map[sid]
                    if s_new_raw.get("state") != s_old["state"]:
                        updated = True
                        new_state = s_new_raw.get("state")
                        logger.info(f"Session {sid} changed state to {new_state}")

                        item["session"]["state"] = new_state
                        item["session"]["updateTime"] = s_new_raw.get("updateTime", "")

                        if new_state == "ACTIVE":
                             if not fcm_token: fcm_token = get_fcm_token(uid, db)
                             send_fcm_message(fcm_token, {
                                "type": "jules_session",
                                "status": "active",
                                "sessionId": sid,
                                "title": s_old.get("title", "")
                            }, notification={
                                "title": "Jules Session Active",
                                "body": f"Session '{s_old.get('title', 'Untitled')}' is now active."
                            })

        # Refetch Active Runs
        if active_runs_indices:
            async with httpx.AsyncClient() as client:
                for list_name, idx, run_id, owner, repo in active_runs_indices:
                    url = f"{GITHUB_API}/repos/{owner}/{repo}/actions/runs/{run_id}"
                    headers = {"Authorization": f"Bearer {github_token}", "Accept": "application/vnd.github.v3+json"}

                    try:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            r_new = resp.json()
                            r_new["_owner"] = owner
                            r_new["_repo"] = repo

                            if list_name == "jointSessions":
                                old_run = joint_sessions[idx]["run"]
                            else:
                                old_run = master_runs[idx]

                            new_status = r_new.get("status")
                            new_conclusion = r_new.get("conclusion")

                            if new_status != old_run["status"] or new_conclusion != old_run["conclusion"]:
                                updated = True

                                artifact_url = old_run.get("artifactUrl")
                                if new_status == "completed" and new_conclusion == "success" and not artifact_url:
                                    artifact_url = await fetch_artifact_url(client, owner, repo, github_token, run_id)

                                updated_run_data = _create_watched_run_data(r_new, artifact_url)

                                if list_name == "jointSessions":
                                    joint_sessions[idx]["run"] = updated_run_data.model_dump()
                                else:
                                    master_runs[idx] = updated_run_data.model_dump()

                                if not fcm_token: fcm_token = get_fcm_token(uid, db)

                                if old_run["status"] != "completed" and new_status == "completed":
                                    msg_data = {
                                        "type": "github_run",
                                        "status": "completed",
                                        "conclusion": new_conclusion,
                                        "runId": str(run_id),
                                        "repo": repo,
                                        "name": r_new.get("name"),
                                        "headBranch": r_new.get("head_branch"),
                                    }
                                    if artifact_url:
                                        msg_data["artifactUrl"] = artifact_url

                                    send_fcm_message(fcm_token, msg_data, notification={
                                        "title": f"Run {new_conclusion.title()}: {r_new.get('name')}",
                                        "body": f"GitHub Action completed on {repo}"
                                    })

                    except Exception as e:
                        logger.error(f"Error updating run {run_id}: {e}")

        if updated:
            data["updatedAt"] = int(time.time() * 1000)
            dashboard_ref.set(data)
            logger.info(f"Dashboard status updated for {uid}")

    except Exception as e:
        logger.error(f"Error in update_dashboard_status for {uid}: {e}")


def _create_watched_run_data(run_dict, artifact_url=None):
    # Helper to convert GitHub API dict to WatchedRunData
    start_time = 0
    try:
        dt = datetime.fromisoformat(run_dict["created_at"].replace("Z", "+00:00"))
        start_time = int(dt.timestamp() * 1000)
    except:
        pass

    head_commit = run_dict.get("head_commit")
    commit_message = head_commit["message"] if head_commit else "No commit message"

    return WatchedRunData(
        runId=run_dict["id"],
        name=run_dict["name"],
        headBranch=run_dict["head_branch"],
        headCommitMessage=commit_message,
        status=run_dict["status"],
        conclusion=run_dict["conclusion"],
        estimatedDuration=0,
        startTime=start_time,
        lastChecked=int(time.time() * 1000),
        progress=0.0,
        artifactUrl=artifact_url,
        htmlUrl=run_dict["html_url"],
        owner=run_dict.get("_owner", ""),
        repo=run_dict.get("_repo", "")
    )


# --- Job Wrappers ---

async def run_dashboard_discovery_job():
    logger.info("Starting Dashboard Discovery job")
    db = get_db()
    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users for Dashboard Discovery")
    for uid, settings_data in users_with_settings:
        await update_dashboard_discovery(uid, settings_data)
    logger.info("Dashboard Discovery job completed")

async def run_dashboard_status_job():
    # logger.debug("Starting Dashboard Status job") # Verbose
    db = get_db()
    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    for uid, settings_data in users_with_settings:
        await update_dashboard_status(uid, settings_data)
