from services.gemini import list_models
from firebase_client import get_db
from firebase_admin import firestore

async def sync_models(uid: str):
    db = get_db()
    settings_ref = db.document(f"users/{uid}/settings/current")
    settings_snap = settings_ref.get()

    if not settings_snap.exists:
        return

    api_key = settings_snap.to_dict().get("apiKey")
    if not api_key:
        return

    try:
        models = await list_models(api_key)

        gen_models = []
        image_models = []

        for m in models:
            methods = m.supported_generation_methods
            if "generateContent" in methods:
                gen_models.append(m.name)
            if "generateImage" in methods: # Assuming this method name for image gen models
                image_models.append(m.name)

        db.document(f"users/{uid}/ai/models").set({
            "generative": gen_models,
            "image": image_models,
            "updatedAt": firestore.SERVER_TIMESTAMP
        })
        print(f"Models synced for {uid}")
    except Exception as e:
        print(f"Model sync error for {uid}: {e}")

async def run_models_sync_job():
    db = get_db()
    users = db.collection("users").stream()
    for user in users:
        await sync_models(user.id)
