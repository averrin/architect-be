from firebase_client import get_db
from firebase_admin import firestore
import threading
from commands.ai_commands import handle_ai_command
from commands.buxfer_commands import handle_buxfer_command
from commands.github_commands import handle_github_command
from commands.gtasks_commands import handle_gtasks_command
from commands.dashboard_commands import handle_dashboard_command
import asyncio

HANDLERS = {
    "ai": handle_ai_command,
    "buxfer": handle_buxfer_command,
    "github": handle_github_command,
    "gtasks": handle_gtasks_command,
    "dashboard": handle_dashboard_command
}

def process_command_sync(doc_snap):
    try:
        asyncio.run(process_command(doc_snap))
    except Exception as e:
        print(f"Error processing command {doc_snap.id}: {e}")

async def process_command(doc_snap):
    data = doc_snap.to_dict()
    cmd_id = doc_snap.id
    ref = doc_snap.reference

    # Path: users/{uid}/.../{domain}/commands/{cmdId}
    path_segments = ref.path.split("/")

    # Strip leading empty segment if present (e.g. from /users/...)
    if path_segments and path_segments[0] == "":
        path_segments = path_segments[1:]

    # Minimum depth: users/{uid}/{domain}/commands/{cmdId} -> 5 segments
    if len(path_segments) < 5:
        return

    # Check that it is under 'users'
    if path_segments[0] != "users":
        return

    uid = path_segments[1]

    # Dynamically find domain in path segments
    # Start searching after uid (index 2 onwards) to avoid collision if uid matches a handler name
    domain = None
    for segment in path_segments[2:]:
        if segment in HANDLERS:
            domain = segment
            break

    if not domain:
        # print(f"No known domain handler found in path: {ref.path}")
        return

    handler = HANDLERS.get(domain)

    print(f"Processing {domain} command {cmd_id} for {uid}")

    ref.update({"status": "processing", "updatedAt": firestore.SERVER_TIMESTAMP})

    try:
        result = await handler(uid, cmd_id, data)

        if domain == "ai":
             db = get_db()
             db.document(f"users/{uid}/ai/results/{cmd_id}").set({
                 "data": result,
                 "completedAt": firestore.SERVER_TIMESTAMP
             })
        else:
             ref.update({"result": result})

        ref.update({"status": "completed", "updatedAt": firestore.SERVER_TIMESTAMP})

    except Exception as e:
        print(f"Command failed: {e}")
        ref.update({
            "status": "failed",
            "error": str(e),
            "updatedAt": firestore.SERVER_TIMESTAMP
        })

def on_snapshot(col_snapshot, changes, read_time):
    for change in changes:
        if change.type.name == 'ADDED':
            doc = change.document
            data = doc.to_dict()
            if data.get('status') == 'pending':
                threading.Thread(target=process_command_sync, args=(doc,)).start()

def start_listener():
    db = get_db()
    print("Starting command listener...")
    # Listen to all 'commands' collections
    watch = db.collection_group('commands').where('status', '==', 'pending').on_snapshot(on_snapshot)
    return watch
