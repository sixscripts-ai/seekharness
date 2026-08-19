import json
import queue
import threading
import time
import uuid
from collections import defaultdict, deque

_queues: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()

_persist_queue: queue.Queue = queue.Queue()
_persist_thread: threading.Thread | None = None


def _persist_worker() -> None:
    # Appwrite rejects documents whose payload exceeds the per-attribute size
    # limit (~64KB). Truncate the artifact body inside any persist call so a
    # long code snippet never kills the durable archive. Live SSE delivery
    # is unaffected because subscribers read from the in-memory queue.
    _MAX_PERSIST_BYTES = 30_000

    def _truncate(value):
        if isinstance(value, str) and len(value) > _MAX_PERSIST_BYTES:
            return value[:_MAX_PERSIST_BYTES] + "\n…[truncated for durable persist]"
        return value

    def _scrub(node):
        if isinstance(node, dict):
            return {k: _scrub(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_scrub(v) for v in node]
        return _truncate(node)

    while True:
        battle_id, event = _persist_queue.get()
        try:
            from . import db

            databases = db.get_databases()
            database_id = db.get_database_id()
            payload = {"type": event.get("type"), "data": _scrub(event.get("data"))}
            databases.create_document(
                database_id,
                "battle_events",
                "unique()",
                {
                    "battle_id": battle_id,
                    "event_id": event["event_id"],
                    "payload": json.dumps(payload),
                    "created_at": float(event["created_at"]),
                },
            )
        except Exception:
            pass


def _ensure_persist_thread() -> None:
    global _persist_thread
    if _persist_thread is None or not _persist_thread.is_alive():
        _persist_thread = threading.Thread(target=_persist_worker, daemon=True)
        _persist_thread.start()


def publish(battle_id: str, event: dict) -> dict:
    """Publish event locally (and optionally durable). Returns enriched event."""
    enriched = {
        **event,
        "event_id": event.get("event_id") or str(uuid.uuid4()),
        "created_at": event.get("created_at") or time.time(),
        "ts": time.time(),
    }
    with _lock:
        _queues[battle_id].append(enriched)
    _persist_async(battle_id, enriched)
    return enriched


def subscribe(battle_id: str) -> list[dict]:
    with _lock:
        return list(_queues[battle_id])


def _persist_async(battle_id: str, event: dict) -> None:
    """Enqueue a durable Appwrite write on a background thread. Never blocks or raises."""
    _ensure_persist_thread()
    _persist_queue.put((battle_id, event))


def load_durable(battle_id: str) -> list[dict]:
    """Load durable events for a battle (uuid + created_at)."""
    try:
        from appwrite.query import Query
        from . import db
        import json

        databases = db.get_databases()
        res = databases.list_documents(
            db.get_database_id(),
            "battle_events",
            queries=[Query.equal("battle_id", battle_id), Query.limit(500)],
        )
        out = []
        for d in res.documents:
            try:
                payload = json.loads(d.data["payload"])
            except Exception:
                payload = {"type": "unknown", "data": {}}
            out.append(
                {
                    "type": payload.get("type", "unknown"),
                    "data": payload.get("data", {}),
                    "event_id": d.data["event_id"],
                    "created_at": float(d.data.get("created_at") or 0),
                }
            )
        out.sort(key=lambda e: (e.get("created_at", 0), e.get("event_id", "")))
        return out
    except Exception:
        return []
