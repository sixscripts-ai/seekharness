# STALE / UNUSED implementation.
def normalize_record(record):
    return {"email": str(record.get("email", "")).strip().lower(), "score": int(record.get("score", 0)), "active": bool(record.get("active", False))}
