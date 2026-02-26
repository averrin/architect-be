from services.gemini import generate_content, configure_genai
from firebase_client import get_db
import json
import base64

async def handle_ai_command(uid, cmd_id, data):
    cmd_type = data.get("type")
    params = data.get("params", {})

    db = get_db()
    settings_snap = db.document(f"users/{uid}/settings/current").get()
    if not settings_snap.exists:
        raise Exception("Settings not found")

    settings = settings_snap.to_dict()
    api_key = settings.get("apiKey")
    if not api_key:
        raise Exception("No Gemini API Key found")

    configure_genai(api_key)

    result = {}

    if cmd_type == "process_content":
        content = params.get("content")
        prompt = params.get("promptOverride") or f"Process this content: {content}"
        resp = await generate_content(api_key, params.get("model", "gemini-pro"), [prompt])
        result = {"text": resp.text}

    elif cmd_type == "analyze_image":
        prompt = params.get("prompt", "Describe this image")
        base64_image = params.get("base64Image")
        mime_type = params.get("mimeType", "image/jpeg")

        contents = [prompt, {"mime_type": mime_type, "data": base64.b64decode(base64_image)}]
        resp = await generate_content(api_key, params.get("model", "gemini-pro-vision"), contents)
        result = {"text": resp.text}

    else:
        # Generic fallback
        prompt = f"Execute command {cmd_type} with params {json.dumps(params)}"
        resp = await generate_content(api_key, params.get("model", "gemini-pro"), [prompt])
        result = {"text": resp.text}

    return result
