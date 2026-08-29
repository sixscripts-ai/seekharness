def normalize_record(record: dict) -> dict:
    """Return a normalized copy with lowercase email and integer score."""
    return {
        "email": str(record.get("email", "")).strip().lower(),
        "score": int(record.get("score", 0)),
        "active": bool(record.get("active", False)),
    }
