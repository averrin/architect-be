from firebase_admin import messaging, firestore
from logger import logger

def get_fcm_token(uid: str, db: firestore.Client) -> str | None:
    """Retrieves the FCM token for a user from Firestore."""
    try:
        doc = db.document(f'users/{uid}/config/fcm').get()
        if doc.exists:
            data = doc.to_dict()
            return data.get('token')
    except Exception as e:
        logger.error(f"Error fetching FCM token for {uid}: {e}")
    return None

def send_fcm_message(token: str, data: dict, notification: dict | None = None):
    """Sends an FCM message to a specific token."""
    if not token:
        return

    try:
        android_config = messaging.AndroidConfig(priority="high")

        message = messaging.Message(
            data=data,
            token=token,
            android=android_config
        )

        if notification:
             message.notification = messaging.Notification(**notification)

        response = messaging.send(message)
        logger.debug(f"FCM message sent to {token[:10]}...: {response} | data={data}")
        return response
    except Exception as e:
        logger.error(f"Failed to send FCM message: {e}")
        return None
