from firebase_admin import messaging, firestore
from firebase_client import get_db
import time
import asyncio
from utils.user_data import get_active_users
from logger import logger

async def run_fcm_heartbeat_job():
    logger.debug("Running FCM Heartbeat job...")
    try:
        db = get_db()
        users = await asyncio.to_thread(get_active_users, db)
        
        for uid, settings in users:
            doc = db.document(f'users/{uid}/config/fcm').get()
            if not doc.exists:
                continue

            data = doc.to_dict()
            token = data.get('token')
            
            if not token:
                continue

            # Send a silent data message
            message = messaging.Message(
                data={
                    "type": "heartbeat",
                    "timestamp": str(int(time.time() * 1000))
                },
                token=token,
                android=messaging.AndroidConfig(
                    priority="normal"
                )
            )

            try:
                response = messaging.send(message)
                print(f"Successfully sent heartbeat message to {uid}: {response}")
            except Exception as e:
                 print(f"Failed to send heartbeat to {uid}: {e}")

    except Exception as e:
        print(f"Error in FCM heartbeat job: {e}")
