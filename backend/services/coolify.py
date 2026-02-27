import httpx
from firebase_client import get_db
from models.coolify import CoolifyDeployment, CoolifyApplication
from firebase_admin import firestore
import time
from logger import logger
from utils.user_data import get_active_users
from utils.fcm import get_fcm_token, send_fcm_message
from config import get_settings
import asyncio

settings = get_settings()

async def fetch_coolify_deployments(client: httpx.AsyncClient, host: str, token: str) -> list[dict]:
    url = f"{host.rstrip('/')}/api/v1/deployments"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = await client.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.error(f"Coolify fetch error ({host}): {e}")
        return []

async def update_coolify_watcher(uid: str, user_settings: dict):
    db = get_db()

    if not user_settings:
        return

    host = user_settings.get("coolifyHost") or settings.COOLIFY_URL
    token = user_settings.get("coolifyToken") or settings.COOLIFY_API_TOKEN

    if not host or not token:
        logger.error(f"No Coolify settings for user {uid}")
        return

    # Load previous state
    ref = db.document(f"users/{uid}/coolify/deployments")
    snap = ref.get()
    old_deployments: dict = {}
    last_updated = 0
    has_active = False

    if snap.exists:
        data = snap.to_dict()
        old_deployments = data.get("deployments", {})
        if data.get("updatedAt"):
            last_updated = data.get("updatedAt").timestamp()
        for d in old_deployments.values():
            if d.get("status") in ["running", "in_progress", "queued"]:
                has_active = True
                break

    current_ts = time.time()

    if not has_active:
        time_diff = current_ts - last_updated
        if time_diff < (settings.COOLIFY_WATCHER_SLOW_INTERVAL_MINUTES * 60):
            logger.debug(f"Skipping Coolify poll for {uid} (slow mode, {int(time_diff)}s ago)")
            return

    logger.info(f"Checking Coolify deployments for {uid}")

    async with httpx.AsyncClient() as client:
        raw = await fetch_coolify_deployments(client, host, token)

    current_ms = int(current_ts * 1000)
    new_deployments: dict = {}
    fcm_token = None
    notifications_sent = 0

    for d in raw:
        uuid = d.get("deployment_uuid") or str(d.get("id", ""))
        if not uuid:
            continue

        status = d.get("status", "")
        old = old_deployments.get(uuid)

        notify_start = False
        notify_complete = False

        if old:
            old_status = old.get("status", "")
            if old_status in ("queued",) and status == "running":
                notify_start = True
            if old_status not in ("finished", "error", "cancelled") and status in ("finished", "error", "cancelled"):
                notify_complete = True
        else:
            if status == "running":
                notify_start = True
            if status in ("finished", "error", "cancelled"):
                notify_complete = True

        app_name = d.get("application_name") or d.get("applicationName") or "Unknown App"
        server_name = d.get("server_name") or d.get("serverName") or ""
        commit_msg = d.get("commit_message") or d.get("commitMessage") or ""
        raw_url = d.get("deployment_url") or d.get("deploymentUrl") or ""
        if raw_url and not raw_url.startswith("http"):
            deployment_url = f"{host.rstrip('/')}{raw_url}"
        else:
            deployment_url = raw_url

        if notify_start:
            if not fcm_token: fcm_token = get_fcm_token(uid, db)
            logger.info(f"Coolify deployment {uuid} started for {app_name}")
            send_fcm_message(fcm_token, {
                "type": "coolify_deployment",
                "status": "running",
                "deploymentUuid": uuid,
                "applicationName": app_name,
                "serverName": server_name,
            }, notification={
                "title": f"Deploy Started: {app_name}",
                "body": f"Server: {server_name}" if server_name else "Coolify deployment started"
            })
            notifications_sent += 1

        if notify_complete:
            if not fcm_token: fcm_token = get_fcm_token(uid, db)
            logger.info(f"Coolify deployment {uuid} completed ({status}) for {app_name}")
            send_fcm_message(fcm_token, {
                "type": "coolify_deployment",
                "status": status,
                "deploymentUuid": uuid,
                "applicationName": app_name,
                "serverName": server_name,
                "deploymentUrl": deployment_url,
            }, notification={
                "title": f"Deploy {status.title()}: {app_name}",
                "body": commit_msg or f"Coolify deployment on {server_name}"
            })
            notifications_sent += 1

        new_deployments[uuid] = CoolifyDeployment(
            id=d.get("id", 0),
            applicationId=str(d.get("application_id") or d.get("applicationId") or ""),
            deploymentUuid=uuid,
            pullRequestId=d.get("pull_request_id") or d.get("pullRequestId") or 0,
            forceRebuild=d.get("force_rebuild") or d.get("forceRebuild") or False,
            commit=d.get("commit"),
            status=status,
            isWebhook=d.get("is_webhook") or d.get("isWebhook") or False,
            isApi=d.get("is_api") or d.get("isApi") or False,
            createdAt=d.get("created_at") or d.get("createdAt") or "",
            updatedAt=d.get("updated_at") or d.get("updatedAt") or "",
            currentProcessId=d.get("current_process_id") or d.get("currentProcessId"),
            restartOnly=d.get("restart_only") or d.get("restartOnly") or False,
            gitType=d.get("git_type") or d.get("gitType"),
            serverId=d.get("server_id") or d.get("serverId"),
            applicationName=app_name,
            serverName=server_name,
            deploymentUrl=deployment_url,
            destinationId=str(d.get("destination_id") or d.get("destinationId") or ""),
            onlyThisServer=d.get("only_this_server") or d.get("onlyThisServer") or False,
            rollback=d.get("rollback") or False,
            commitMessage=commit_msg,
            lastChecked=current_ms,
        ).model_dump()

    new_keys = set(new_deployments.keys())
    old_keys = set(old_deployments.keys())
    deployments_changed = new_keys != old_keys or any(
        new_deployments[k]["status"] != old_deployments.get(k, {}).get("status")
        for k in new_keys
    )

    if deployments_changed or not raw:
        ref.set({
            "deployments": new_deployments,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Coolify deployments updated for {uid}: {len(new_deployments)} tracked (sent {notifications_sent} notifications)")

    return deployments_changed

async def fetch_coolify_applications(client: httpx.AsyncClient, host: str, token: str) -> list[dict]:
    url = f"{host.rstrip('/')}/api/v1/applications"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = await client.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.error(f"Coolify applications fetch error ({host}): {e}")
        return []

async def fetch_coolify_env_map(client: httpx.AsyncClient, host: str, token: str) -> dict[int, dict]:
    url = f"{host.rstrip('/')}/api/v1/projects"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    env_map = {}
    try:
        resp = await client.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        projects = resp.json()
        if not isinstance(projects, list):
            return {}
        for p in projects:
            p_uuid = p.get("uuid")
            if not p_uuid:
                continue
            p_env_url = f"{host.rstrip('/')}/api/v1/projects/{p_uuid}/environments"
            try:
                env_resp = await client.get(p_env_url, headers=headers, timeout=15)
                env_resp.raise_for_status()
                envs = env_resp.json()
                if isinstance(envs, list):
                    for env in envs:
                        env_id = env.get("id")
                        if env_id:
                            env_map[env_id] = {
                                "projectUuid": p_uuid,
                                "environmentUuid": env.get("uuid")
                            }
            except Exception as e:
                logger.debug(f"Failed to fetch envs for project {p_uuid}: {e}")
    except Exception as e:
        logger.error(f"Coolify projects fetch error ({host}): {e}")
    return env_map

async def update_coolify_applications(uid: str, host: str, token: str, force: bool = False):
    db = get_db()
    ref = db.document(f"users/{uid}/coolify/applications")
    snap = ref.get()
    last_updated = 0

    if snap.exists:
        data = snap.to_dict()
        if data.get("updatedAt"):
            last_updated = data.get("updatedAt").timestamp()

    current_ts = time.time()
    time_diff = current_ts - last_updated
    if not force and time_diff < (settings.COOLIFY_APPS_SLOW_INTERVAL_MINUTES * 60):
        logger.debug(f"Skipping Coolify apps poll for {uid} ({int(time_diff)}s ago)")
        return

    logger.info(f"Checking Coolify applications for {uid}")

    async with httpx.AsyncClient() as client:
        raw = await fetch_coolify_applications(client, host, token)
        env_map = await fetch_coolify_env_map(client, host, token) if raw else {}

    if not raw:
        return

    current_ms = int(current_ts * 1000)
    old_apps: dict = snap.to_dict().get("applications", {}) if snap.exists else {}
    apps: dict = {}
    fcm_token = None

    for a in raw:
        uuid = a.get("uuid")
        if not uuid:
            continue
        status = a.get("status") or "unknown"
        name = a.get("name") or uuid
        old_status = old_apps.get(uuid, {}).get("status")

        if old_status is not None and old_status != status:
            if not fcm_token: fcm_token = get_fcm_token(uid, db)
            logger.info(f"Coolify app {name} status: {old_status} → {status}")
            send_fcm_message(fcm_token, {
                "type": "coolify_app",
                "appUuid": uuid,
                "applicationName": name,
                "status": status,
                "previousStatus": old_status,
            }, notification={
                "title": f"{name}: {status.title()}",
                "body": f"Was {old_status}"
            })

        env_id = a.get("environment_id")
        mapped_env = env_map.get(env_id, {}) if env_id else {}

        apps[uuid] = CoolifyApplication(
            id=a.get("id", 0),
            uuid=uuid,
            name=name,
            fqdn=a.get("fqdn"),
            status=status,
            gitRepository=a.get("git_repository"),
            gitBranch=a.get("git_branch"),
            buildPack=a.get("build_pack"),
            projectUuid=mapped_env.get("projectUuid"),
            environmentUuid=mapped_env.get("environmentUuid"),
            lastChecked=current_ms,
        ).model_dump()

    ref.set({
        "applications": apps,
        "updatedAt": firestore.SERVER_TIMESTAMP
    })
    logger.info(f"Coolify applications updated for {uid}: {len(apps)} apps")

async def control_coolify_application(host: str, token: str, app_uuid: str, action: str) -> dict:
    valid_actions = {"start", "stop", "restart"}
    if action not in valid_actions:
        raise ValueError(f"Invalid action: {action}")
    url = f"{host.rstrip('/')}/api/v1/applications/{app_uuid}/{action}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

async def run_coolify_job():
    logger.info("Starting Coolify job")
    db = get_db()

    try:
        users_with_settings = await asyncio.to_thread(get_active_users, db)
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return

    logger.info(f"Found {len(users_with_settings)} users to process for Coolify")

    for uid, settings_data in users_with_settings:
        host = settings_data.get("coolifyHost") or settings.COOLIFY_URL
        token = settings_data.get("coolifyToken") or settings.COOLIFY_API_TOKEN
        if not host or not token:
            continue
        deployments_changed = await update_coolify_watcher(uid, settings_data)
        await update_coolify_applications(uid, host, token, force=deployments_changed)

    logger.info("Coolify job completed")
