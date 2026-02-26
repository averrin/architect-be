import firebase_admin
from firebase_admin import credentials, firestore
from config import get_settings
import os
import json

settings = get_settings()

def init_firebase():
    if not firebase_admin._apps:
        cred = None
        if settings.FIREBASE_SERVICE_ACCOUNT_JSON:
            if os.path.exists(settings.FIREBASE_SERVICE_ACCOUNT_JSON):
                cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
            else:
                try:
                    service_account_info = json.loads(settings.FIREBASE_SERVICE_ACCOUNT_JSON)
                    cred = credentials.Certificate(service_account_info)
                except json.JSONDecodeError:
                    pass

        if cred:
            firebase_admin.initialize_app(cred, {'projectId': settings.FIREBASE_PROJECT_ID})
        else:
            firebase_admin.initialize_app(options={'projectId': settings.FIREBASE_PROJECT_ID})

def get_db():
    return firestore.client()
