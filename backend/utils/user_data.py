import json
from logger import logger

def parse_settings(doc_snapshot):
    """
    Parses the settings document.
    Handles the case where settings are stored as a JSON string inside a 'data' field,
    and wrapped in a 'state' object.
    """
    if not doc_snapshot.exists:
        return {}

    data = doc_snapshot.to_dict()
    if not data:
        return {}

    # Check if 'data' field contains a JSON string (as seen in user image)
    if "data" in data and isinstance(data["data"], str):
        try:
            parsed = json.loads(data["data"])
            # The structure in the image is {"state": {...}}
            if "state" in parsed:
                return parsed["state"]
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse settings JSON for {doc_snapshot.reference.path}: {e}")
            # If parsing fails, maybe return the raw data or empty?
            # Returning raw data as fallback might be safer if structure varies.
            return data

    # If not a string in 'data', maybe it's direct fields?
    return data

def get_active_users(db):
    """
    Finds active users by looking for their settings.
    This handles cases where the parent 'users/{uid}' document might not exist (phantom document).
    Returns a list of tuples: (uid, settings_dict)
    """
    users_with_settings = []

    # We look for documents in the 'settings' collection group.
    # We expect documents named 'current'.
    # Note: Querying collection_group without index is fine for small datasets or if no filters are applied.
    # We iterate and filter by ID in code to avoid index requirements for now.

    try:
        # Stream all documents in any 'settings' collection
        # This is more robust than iterating 'users' collection if user docs are missing.
        settings_docs = db.collection_group("settings").stream()

        count = 0
        for doc in settings_docs:
            if doc.id == "current":
                # The parent of 'current' is the 'settings' collection.
                # The parent of 'settings' collection is the user document.
                # Path: users/{uid}/settings/current
                user_ref = doc.reference.parent.parent
                if user_ref:
                    uid = user_ref.id
                    settings = parse_settings(doc)
                    users_with_settings.append((uid, settings))
                    count += 1

        if count == 0:
            logger.debug("No settings/current documents found via collection group.")

    except Exception as e:
        logger.error(f"Error querying settings collection group: {e}")
        return []

    return users_with_settings
