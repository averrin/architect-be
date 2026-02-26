import sys
import os
import time
import uuid

# Add parent directory to path so we can import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from firebase_client import init_firebase, get_db
from firebase_admin import firestore
import threading

def run_test(uid, content):
    init_firebase()
    db = get_db()

    cmd_id = str(uuid.uuid4())

    print(f"Creating command {cmd_id} for user {uid}...")

    cmd_ref = db.document(f"users/{uid}/ai/commands/{cmd_id}")
    cmd_ref.set({
        "type": "process_content",
        "params": {
            "content": content,
            "model": "gemini-pro"
        },
        "status": "pending",
        "createdAt": firestore.SERVER_TIMESTAMP
    })

    print("Command created. Waiting for result...")

    result_ref = db.document(f"users/{uid}/ai/results/{cmd_id}")

    # Simple polling for result
    for _ in range(30):
        snap = result_ref.get()
        if snap.exists:
            print("\nResult received:")
            print(snap.to_dict())
            return
        time.sleep(1)
        print(".", end="", flush=True)

    print("\nTimeout waiting for result.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python test_command.py <uid> <content>")
        sys.exit(1)

    uid = sys.argv[1]
    content = sys.argv[2]

    run_test(uid, content)
