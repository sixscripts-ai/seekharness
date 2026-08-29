"""Read-only Appwrite -> PostgreSQL (Neon) backfill for the Agent Arena.

Migrates the Phase 1 PostgreSQL persistence layer (SQLAlchemy 2.x models in
agent_arena.persistence.models) from the Appwrite project configured in .env.
Appwrite is treated as a STRICTLY READ-ONLY source: this script never issues a
create/update/delete against Appwrite, never decrypts provider keys (Fernet
ciphertext is copied as-is), and never prints secrets.

Idempotent: safe to re-run. Existing destination rows are preserved (IDs are
kept from Appwrite, and unique-constrained relations are handled with
ON CONFLICT semantics), so repeated runs converge to the same state.

Usage (from backend/):
  ./.venv/bin/python scripts/backfill_appwrite_to_postgres.py          # run backfill
  ./.venv/bin/python scripts/backfill_appwrite_to_postgres.py --verify # only verify/report

See scripts/verify_backfill.py for the standalone (framework-free) verifier.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the backend package is importable when run as a script.
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------------------------------------------------------------------------
# Secret-safe reporting primitives
# ---------------------------------------------------------------------------

# Keys that must never appear in any report/log/output.
_NEVER_OUTPUT_FIELDS = {
    "encrypted_key", "DATABASE_URL", "DATABASE_URL_UNPOOLED", "APPWRITE_API_KEY",
    "FERNET_KEY", "FERNET_KEY_OLD", "INTERNAL_API_KEY",
}


def _sane(value) -> str:
    """Render a field value for a report, redacting anything secret-shaped."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    s = str(value)
    return s if s else "<empty>"


# ---------------------------------------------------------------------------
# Datetime conversion
# ---------------------------------------------------------------------------

def to_tz_datetime(raw) -> datetime | None:
    """Convert an Appwrite timestamp (epoch float, ISO string, or datetime) to
    a tz-aware UTC datetime. Returns None when the value is absent/None."""
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        dt = raw
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    # epoch-as-string
    try:
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        pass
    # ISO 8601
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_model_ids(raw):
    """Parse the serialized model_ids. Returns a list[str], or None on failure.

    Appwrite stores model_ids as a JSON-string of a list (legacy) but also
    tolerates a bare comma-separated string and an already-parsed list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if not isinstance(raw, str):
        raw = str(raw)
    raw = raw.strip()
    if not raw:
        return []
    # JSON list
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    except (json.JSONDecodeError, TypeError):
        pass
    # comma separated fallback
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if parts:
        return parts
    return None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _list_all(databases, database_id, collection, *, limit=1000):
    """Read every document in a collection (paginated). Raises on transport
    errors (including Appwrite HTTP 402 quota exhaustion) so callers can
    decide whether to abort that collection or the whole run."""
    from appwrite.query import Query

    out = []
    offset = 0
    while True:
        res = databases.list_documents(
            database_id, collection, queries=[Query.limit(limit), Query.offset(offset)]
        )
        batch = list(res.documents)
        out.extend(batch)
        # tablesdb rows expose data via document.data; this helper returns the
        # raw document objects, and callers use _doc_meta() uniformly.
        if len(batch) < limit:
            break
        offset += limit
    return out


def _doc_meta(doc) -> dict:
    """Extract {data, id, createdat, updatedat} from a tablesdb Document."""
    # New Appwrite SDK returns Pydantic Document with .data/.id/.createdat.
    if isinstance(doc, dict):
        data = dict(doc.get("data", doc))
    else:
        data = dict(getattr(doc, "data", {}) or {})
    doc_id = doc.get("$id") if isinstance(doc, dict) else getattr(doc, "id", None)
    if doc_id is None and isinstance(data, dict):
        doc_id = data.get("$id")
    createdat = doc.get("$createdAt") if isinstance(doc, dict) else getattr(doc, "createdat", None)
    updatedat = doc.get("$updatedAt") if isinstance(doc, dict) else getattr(doc, "updatedat", None)
    return {"data": data, "id": doc_id, "createdat": createdat, "updatedat": updatedat}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="only report counts/integrity")
    args = parser.parse_args(argv)

    from agent_arena import db
    from agent_arena.persistence import session_scope
    from agent_arena.persistence import models as M

    # ---- Appwrite source (read-only) -------------------------------------
    databases = db.get_databases()
    database_id = db.get_database_id()

    # ---- collections in dependency order ---------------------------------
    collections = [
        "formats",
        "providers",
        "battles",
        "battle_drafts",
        "battle_events",
        "rounds",
        "scores",
        "leaderboard",
        "skills",
        "memories",
    ]

    report = {"source": {}, "dest": {}, "anomalies": [], "unknown_fields": {}}

    # Load source documents first (best-effort per collection).
    source: dict[str, list] = {}
    failed: dict[str, str] = {}
    for coll in collections:
        try:
            source[coll] = _list_all(databases, database_id, coll)
            report["source"][coll] = len(source[coll])
        except Exception as exc:
            failed[coll] = exc
            source[coll] = []
            report["source"][coll] = f"FAILED"

    if args.verify:
        # Read-only: report source vs destination counts and integrity only.
        return _verify_only(source, report, failed)

    # We perform the actual inserts in smaller scopes per collection so a
    # single bad row does not abort everything.
    stats = {}

    # ---- formats ---------------------------------------------------------
    stats["formats"] = _migrate_formats(source["formats"], report, failed)
    # ---- providers -------------------------------------------------------
    stats["providers"] = _migrate_providers(source["providers"], report, failed)
    # ---- battles + participants -----------------------------------------
    stats["battles"], stats["battle_participants"] = _migrate_battles(
        source["battles"], report, failed
    )
    # ---- battle_drafts ---------------------------------------------------
    stats["battle_drafts"] = _migrate_drafts(source["battle_drafts"], report, failed)
    # ---- battle_events ---------------------------------------------------
    stats["battle_events"] = _migrate_events(source["battle_events"], report, failed)
    # ---- rounds ----------------------------------------------------------
    stats["rounds"] = _migrate_rounds(source["rounds"], report, failed)
    # ---- scores ----------------------------------------------------------
    stats["scores"] = _migrate_scores(source["scores"], report, failed)
    # ---- leaderboard -----------------------------------------------------
    stats["leaderboard"] = _migrate_leaderboard(source["leaderboard"], report, failed)
    # ---- skills ----------------------------------------------------------
    stats["skills"] = _migrate_skills(source["skills"], report, failed)
    # ---- memories --------------------------------------------------------
    stats["memories"] = _migrate_memories(source["memories"], report, failed)

    # ---- emit report -----------------------------------------------------
    _emit_report(report, stats, failed)

    # ---- destination counts ---------------------------------------------
    print("\n[DESTINATION COUNTS]")
    dest = _destination_counts()
    for tbl in _TABLE_LIST:
        print(f"  {tbl}: {dest[tbl]}")
        stats[tbl] = dest[tbl]

    return 0


_TABLE_LIST = [
    "formats", "providers", "battles", "battle_participants",
    "battle_drafts", "battle_events", "rounds", "scores",
    "leaderboard", "skills", "memories",
]


# Map destination report table name -> model class.
_TABLE_MAP = {
    "formats": "Format",
    "providers": "Provider",
    "battles": "Battle",
    "battle_participants": "BattleParticipant",
    "battle_drafts": "BattleDraft",
    "battle_events": "BattleEvent",
    "rounds": "Round",
    "scores": "Score",
    "leaderboard": "LeaderboardEntry",
    "skills": "SkillRecord",
    "memories": "Memory",
}


def _destination_counts() -> dict:
    from sqlalchemy import select, func
    from agent_arena.persistence import session_scope
    from agent_arena.persistence import models as M

    out = {}
    with session_scope() as s:
        for tbl in _TABLE_LIST:
            out[tbl] = s.execute(
                select(func.count()).select_from(getattr(M, _TABLE_MAP[tbl]))
            ).scalar()
    return out


def _verify_only(source, report, failed) -> int:
    """Read-only comparison of source vs destination (no writes)."""
    from collections import Counter

    print("==== VERIFY (read-only) ====")
    dest = _destination_counts()
    print("\n[SOURCE vs DESTINATION COUNTS]")
    for coll in _TABLE_LIST:
        src = report["source"].get(coll, "?")
        print(f"  {coll:<20} source={src:<8} dest={dest.get(coll, '?')}")

    print("\n[PARTICIPANTS SUM vs BATTLES]")
    print(f"  battle_participants={dest['battle_participants']}  battles={dest['battles']}")

    print("\n[COLLECTIONS FAILED]")
    if failed:
        for coll, exc in failed.items():
            code = getattr(exc, "code", None)
            print(f"  {coll}: {type(exc).__name__}" + (f" (HTTP {code})" if code else ""))
    else:
        print("  (none)")

    print("\n[UNKNOWN LIVE FIELDS]")
    uf = report["unknown_fields"]
    if uf:
        for coll, counts in sorted(uf.items()):
            for fname, cnt in sorted(counts.items()):
                print(f"  {coll}.{fname}: {cnt}")
    else:
        print("  (none)")

    print("\n[ANOMALIES]")
    if report["anomalies"]:
        for a in report["anomalies"]:
            print("  " + a)
    else:
        print("  (none)")

    # orphan / duplicate identity reporting during verify: recompute lightweight
    # checks over the SOURCE data without touching Postgres.
    _verify_orphans_and_dupes(source, report)

    print("==== END VERIFY ====")
    return 0


def _verify_orphans_and_dupes(source, report) -> None:
    """Report orphans/duplicates from source data alone (no destination reads)."""
    from collections import Counter

    print("\n[SOURCE ORPHANS / DUPLICATES]")
    battle_ids = {_doc_meta(d)["id"] for d in source.get("battles", [])}

    for coll, fk in (("battle_events", "battle_id"), ("rounds", "battle_id"), ("scores", "battle_id")):
        orphans = 0
        for doc in source.get(coll, []):
            meta = _doc_meta(doc)
            if meta["data"].get(fk) not in battle_ids:
                orphans += 1
        print(f"  {coll} orphan rows: {orphans}")

    # scores duplicates by (battle_id, model_id)
    sc = Counter()
    for doc in source.get("scores", []):
        d = _doc_meta(doc)["data"]
        sc[(d.get("battle_id"), d.get("model_id"))] += 1
    dup_scores = {k: v for k, v in sc.items() if v > 1}
    print(f"  scores duplicate identities: {len(dup_scores)}" + (f" {dup_scores}" if dup_scores else ""))

    lb = Counter()
    for doc in source.get("leaderboard", []):
        d = _doc_meta(doc)["data"]
        lb[(d.get("model_id"), d.get("format_id"))] += 1
    dup_lb = {k: v for k, v in lb.items() if v > 1}
    print(f"  leaderboard duplicate identities: {len(dup_lb)}" + (f" {dup_lb}" if dup_lb else ""))


def _emit_report(report, stats, failed):
    print("\n==== BACKFILL REPORT ====")
    print("\n[SOURCE -> DESTINATION COUNTS]")
    colls = list(report["source"].keys())
    for coll in colls:
        src = report["source"][coll]
        dst = stats.get(coll, "?")
        print(f"  {coll:<20} source={src:<8} dest={dst}")
    print("\n[COLLECTIONS FAILED]")
    if failed:
        for coll, exc in failed.items():
            code = getattr(exc, "code", None)
            print(f"  {coll}: {type(exc).__name__}" + (f" (HTTP {code})" if code else ""))
    else:
        print("  (none)")
    print("\n[UNKNOWN LIVE FIELDS]")
    uf = report["unknown_fields"]
    if uf:
        for coll, counts in sorted(uf.items()):
            for fname, cnt in sorted(counts.items()):
                print(f"  {coll}.{fname}: {cnt}")
    else:
        print("  (none)")
    print("\n[ANOMALIES]")
    if report["anomalies"]:
        for a in report["anomalies"]:
            print("  " + a)
    else:
        print("  (none)")
    print("\n==== END REPORT ====")


# ---------------------------------------------------------------------------
# Per-collection migration functions (each uses its own short transaction)
# ---------------------------------------------------------------------------

def _migrate_formats(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import Format
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import select, func

    KNOWN = {"name", "engine", "config"}
    inserted = skipped_existing = 0
    rows = []
    for doc in src:
        meta = _doc_meta(doc)
        data = meta["data"]
        docid = meta["id"]
        # unknown field detection
        for f in data.keys():
            if f not in KNOWN:
                report["unknown_fields"].setdefault("formats", {})
                report["unknown_fields"]["formats"][f] = report["unknown_fields"]["formats"].get(f, 0) + 1
        raw_config = data.get("config")
        if isinstance(raw_config, str):
            try:
                config = json.loads(raw_config)
            except (json.JSONDecodeError, TypeError):
                config = {}
                report["anomalies"].append(f"format {docid}: config is not valid JSON; stored as empty JSONB")
        elif isinstance(raw_config, dict):
            config = raw_config
        else:
            config = {}
        rows.append({
            "id": docid,
            "name": data.get("name") or "",
            "engine": data.get("engine") or "",
            "config": config,
        })
    if rows:
        with session_scope() as s:
            for r in rows:
                stmt = (
                    pg_insert(Format)
                    .values(**r)
                    .on_conflict_do_nothing(constraint="formats_pkey")
                )
                s.execute(stmt)
    return len(rows)


def _migrate_providers(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import Provider
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    KNOWN = {"user_id", "name", "base_url", "encrypted_key", "masked_key",
             "auth_style", "model_name"}
    rows = []
    for doc in src:
        meta = _doc_meta(doc)
        data = meta["data"]
        docid = meta["id"]
        for f in data.keys():
            if f not in KNOWN:
                report["unknown_fields"].setdefault("providers", {})
                report["unknown_fields"]["providers"][f] = report["unknown_fields"]["providers"].get(f, 0) + 1
        rows.append({
            "id": docid,
            "user_id": data.get("user_id") or "",
            "name": data.get("name") or "",
            "base_url": data.get("base_url") or "",
            # encrypted_key: ciphertext copied verbatim; never decrypted, never printed
            "encrypted_key": data.get("encrypted_key") or "",
            "masked_key": data.get("masked_key") or "",
            "auth_style": data.get("auth_style") or "bearer",
            "model_name": data.get("model_name") or "",
        })
    if rows:
        with session_scope() as s:
            for r in rows:
                stmt = (
                    pg_insert(Provider)
                    .values(**r)
                    .on_conflict_do_nothing(constraint="providers_pkey")
                )
                s.execute(stmt)
    return len(rows)


_BATTLE_KNOWN = {
    "user_id", "format_id", "model_ids", "arena_size", "status",
    "timeout_seconds", "round_visibility", "saved", "sandbox_id",
    "judge_provider_id", "preview_urls", "failure_reason", "started_at",
    "completed_at", "difficulty", "draft_id", "battle_config", "spec_hash",
    "custom_title", "ranked", "target_id", "target_version",
    "target_manifest_hash",
}


def _migrate_battles(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import Battle, BattleParticipant
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import select

    battles = []
    participants = []
    skipped_unparseable = []
    for doc in src:
        meta = _doc_meta(doc)
        data = meta["data"]
        docid = meta["id"]
        for f in data.keys():
            if f not in _BATTLE_KNOWN:
                report["unknown_fields"].setdefault("battles", {})
                report["unknown_fields"]["battles"][f] = report["unknown_fields"]["battles"].get(f, 0) + 1
        model_ids = parse_model_ids(data.get("model_ids"))
        if model_ids is None:
            skipped_unparseable.append(docid)
            report["anomalies"].append(f"battle {docid}: model_ids unparseable, SKIPPED")
            continue
        # timestamps
        started_at = to_tz_datetime(data.get("started_at")) or to_tz_datetime(meta["createdat"])
        completed_at = to_tz_datetime(data.get("completed_at"))
        created_at = to_tz_datetime(meta["createdat"]) or datetime.now(timezone.utc)
        updated_at = to_tz_datetime(meta["updatedat"]) or created_at

        preview_urls = data.get("preview_urls")
        if isinstance(preview_urls, str):
            try:
                preview_urls = json.loads(preview_urls)
            except (json.JSONDecodeError, TypeError):
                preview_urls = None
        battle_config = data.get("battle_config")
        if isinstance(battle_config, str):
            try:
                battle_config = json.loads(battle_config)
            except (json.JSONDecodeError, TypeError):
                battle_config = None

        target_id = data.get("target_id")
        target_manifest_hash = data.get("target_manifest_hash")
        spec_hash = data.get("spec_hash")
        if target_id and not target_manifest_hash:
            target_manifest_hash = spec_hash

        arena_size = data.get("arena_size")
        try:
            arena_size = int(arena_size) if arena_size is not None else len(model_ids)
        except (TypeError, ValueError):
            arena_size = len(model_ids)

        row = {
            "id": docid,
            "user_id": data.get("user_id") or "",
            "format_id": data.get("format_id") or "",
            "arena_size": arena_size,
            "status": data.get("status") or "queued",
            "timeout_seconds": int(data.get("timeout_seconds") or 0),
            "round_visibility": data.get("round_visibility") or "",
            "saved": bool(data.get("saved")),
            "sandbox_id": data.get("sandbox_id"),
            "judge_provider_id": data.get("judge_provider_id"),
            "preview_urls": preview_urls,
            "failure_reason": data.get("failure_reason"),
            "started_at": started_at,
            "completed_at": completed_at,
            "difficulty": data.get("difficulty"),
            "draft_id": data.get("draft_id"),
            "battle_config": battle_config,
            "spec_hash": spec_hash,
            "custom_title": data.get("custom_title"),
            "ranked": data.get("ranked"),
            "target_id": target_id,
            "target_version": data.get("target_version"),
            "target_manifest_hash": target_manifest_hash,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        battles.append(row)
        for position, mid in enumerate(model_ids):
            participants.append({
                "battle_id": docid,
                "position": position,
                "model_id": mid,
                "role": None,
            })

    if battles:
        with session_scope() as s:
            for r in battles:
                s.execute(pg_insert(Battle).values(**r).on_conflict_do_nothing(constraint="battles_pkey"))
            for r in participants:
                s.execute(
                    pg_insert(BattleParticipant)
                    .values(**r)
                    .on_conflict_do_nothing(constraint="battle_participants_pkey")
                )
    return len(battles), len(participants)


def _migrate_drafts(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import BattleDraft
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    KNOWN = {"user_id", "mode", "transcript", "spec", "revision", "status",
             "launched_battle_id", "architect_error"}
    rows = []
    for doc in src:
        meta = _doc_meta(doc)
        data = meta["data"]
        docid = meta["id"]
        for f in data.keys():
            if f not in KNOWN:
                report["unknown_fields"].setdefault("battle_drafts", {})
                report["unknown_fields"]["battle_drafts"][f] = report["unknown_fields"]["battle_drafts"].get(f, 0) + 1
        transcript = data.get("transcript")
        if isinstance(transcript, str):
            try:
                transcript = json.loads(transcript)
            except (json.JSONDecodeError, TypeError):
                transcript = []
        if not isinstance(transcript, list):
            transcript = []
        spec = data.get("spec")
        if isinstance(spec, str):
            try:
                spec = json.loads(spec)
            except (json.JSONDecodeError, TypeError):
                spec = {}
        if not isinstance(spec, dict):
            spec = {}
        created_at = to_tz_datetime(data.get("created_at")) or to_tz_datetime(meta["createdat"])
        updated_at = to_tz_datetime(data.get("updated_at")) or to_tz_datetime(meta["updatedat"]) or created_at
        rows.append({
            "id": docid,
            "user_id": data.get("user_id") or "",
            "mode": data.get("mode") or "",
            "transcript": transcript,
            "spec": spec,
            "revision": int(data.get("revision") or 0),
            "status": data.get("status") or "drafting",
            "launched_battle_id": data.get("launched_battle_id"),
            "architect_error": data.get("architect_error"),
            "created_at": created_at,
            "updated_at": updated_at,
        })
    if rows:
        with session_scope() as s:
            for r in rows:
                s.execute(pg_insert(BattleDraft).values(**r).on_conflict_do_nothing(constraint="battle_drafts_pkey"))
    return len(rows)


def _migrate_events(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import BattleEvent, Battle
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import select

    KNOWN = {"battle_id", "event_id", "payload", "created_at"}
    rows = []
    orphan = 0
    dup = 0
    with session_scope() as s:
        existing_battles = set(s.scalars(select(Battle.id)).all())
        for doc in src:
            meta = _doc_meta(doc)
            data = meta["data"]
            docid = meta["id"]
            for f in data.keys():
                if f not in KNOWN:
                    report["unknown_fields"].setdefault("battle_events", {})
                    report["unknown_fields"]["battle_events"][f] = report["unknown_fields"]["battle_events"].get(f, 0) + 1
            battle_id = data.get("battle_id")
            event_id = data.get("event_id") or docid
            if battle_id not in existing_battles:
                orphan += 1
                report["anomalies"].append(f"battle_event {docid}: orphan (battle {battle_id} missing), SKIPPED")
                continue
            # parse payload JSON string -> derive event_type + payload
            raw_payload = data.get("payload")
            if isinstance(raw_payload, str):
                try:
                    parsed = json.loads(raw_payload)
                except (json.JSONDecodeError, TypeError):
                    parsed = {"type": "unknown", "data": {"_raw": raw_payload}}
            elif isinstance(raw_payload, dict):
                parsed = raw_payload
            else:
                parsed = {"type": "unknown", "data": {}}
            event_type = parsed.get("type") or parsed.get("event") or "unknown"
            payload = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
            # preserve the full envelope when the stored shape is not {type, data}
            if "type" not in parsed and "event" not in parsed:
                payload = parsed
            created_at = to_tz_datetime(data.get("created_at")) or to_tz_datetime(meta["createdat"])
            rows.append({
                "battle_id": battle_id,
                "event_id": event_id,
                "event_type": str(event_type),
                "sequence": None,
                "payload": payload,
                "created_at": created_at,
            })
        for r in rows:
            s.execute(
                pg_insert(BattleEvent)
                .values(**r)
                .on_conflict_do_nothing(constraint="uq_battle_events_event_id")
            )
    return len(rows)


def _migrate_rounds(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import Round, Battle
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import select

    KNOWN = {"battle_id", "phase", "model_id", "artifact"}
    rows = []
    orphan = 0
    with session_scope() as s:
        existing_battles = set(s.scalars(select(Battle.id)).all())
        for doc in src:
            meta = _doc_meta(doc)
            data = meta["data"]
            docid = meta["id"]
            for f in data.keys():
                if f not in KNOWN:
                    report["unknown_fields"].setdefault("rounds", {})
                    report["unknown_fields"]["rounds"][f] = report["unknown_fields"]["rounds"].get(f, 0) + 1
            battle_id = data.get("battle_id")
            if battle_id not in existing_battles:
                orphan += 1
                report["anomalies"].append(f"round {docid}: orphan (battle {battle_id} missing), SKIPPED")
                continue
            rows.append({
                "id": docid,
                "battle_id": battle_id,
                "phase": data.get("phase") or "",
                "model_id": data.get("model_id") or "",
                "artifact": data.get("artifact"),
            })
        for r in rows:
            s.execute(pg_insert(Round).values(**r).on_conflict_do_nothing(constraint="rounds_pkey"))
    return len(rows)


def _migrate_scores(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import Score, Battle
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy import select
    from collections import Counter

    KNOWN = {"battle_id", "model_id", "score", "judge_model", "justification"}
    rows = []
    orphan = 0
    dup_counter = Counter()
    with session_scope() as s:
        existing_battles = set(s.scalars(select(Battle.id)).all())
        seen_keys = Counter()
        order = []
        for doc in src:
            meta = _doc_meta(doc)
            data = meta["data"]
            docid = meta["id"]
            for f in data.keys():
                if f not in KNOWN:
                    report["unknown_fields"].setdefault("scores", {})
                    report["unknown_fields"]["scores"][f] = report["unknown_fields"]["scores"].get(f, 0) + 1
            battle_id = data.get("battle_id")
            model_id = data.get("model_id")
            if battle_id not in existing_battles:
                orphan += 1
                report["anomalies"].append(f"score {docid}: orphan (battle {battle_id} missing), SKIPPED")
                continue
            key = (battle_id, model_id)
            if seen_keys[key] > 0:
                dup_counter[key] += 1
                continue  # keep first
            seen_keys[key] += 1
            rows.append({
                "id": docid,
                "battle_id": battle_id,
                "model_id": model_id or "",
                "score": float(data.get("score") or 0),
                "judge_model": data.get("judge_model"),
                "justification": data.get("justification"),
            })
        for (b, m), c in dup_counter.items():
            report["anomalies"].append(f"scores duplicate (battle_id, model_id)=({b},{m}) count={c + 1}; kept first")
        for r in rows:
            s.execute(pg_insert(Score).values(**r).on_conflict_do_nothing(constraint="uq_scores_battle_model"))
    return len(rows)


def _migrate_leaderboard(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import LeaderboardEntry
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from collections import Counter

    KNOWN = {"model_id", "format_id", "elo", "games_played"}
    rows = []
    dup_counter = Counter()
    with session_scope() as s:
        seen_keys = Counter()
        for doc in src:
            meta = _doc_meta(doc)
            data = meta["data"]
            docid = meta["id"]
            for f in data.keys():
                if f not in KNOWN:
                    report["unknown_fields"].setdefault("leaderboard", {})
                    report["unknown_fields"]["leaderboard"][f] = report["unknown_fields"]["leaderboard"].get(f, 0) + 1
            model_id = data.get("model_id")
            scope = data.get("format_id")  # Appwrite format_id -> scope
            key = (model_id, scope)
            if seen_keys[key] > 0:
                dup_counter[key] += 1
                continue  # keep first
            seen_keys[key] += 1
            rows.append({
                "model_id": model_id or "",
                "scope": scope or "",
                "elo": float(data.get("elo") or 0),
                "games_played": int(data.get("games_played") or 0),
            })
        for (m, sc), c in dup_counter.items():
            report["anomalies"].append(f"leaderboard duplicate (model_id, scope)=({m},{sc}) count={c + 1}; kept first")
        for r in rows:
            s.execute(
                pg_insert(LeaderboardEntry)
                .values(**r)
                .on_conflict_do_nothing(constraint="leaderboard_pkey")
            )
    return len(rows)


def _migrate_skills(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import SkillRecord
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    KNOWN = {"skill", "elo", "wins", "losses", "draws", "uses",
             "success_rate", "tier", "tags", "last_used"}
    rows = []
    for doc in src:
        meta = _doc_meta(doc)
        data = meta["data"]
        docid = meta["id"]
        for f in data.keys():
            if f not in KNOWN:
                report["unknown_fields"].setdefault("skills", {})
                report["unknown_fields"]["skills"][f] = report["unknown_fields"]["skills"].get(f, 0) + 1
        tags = data.get("tags")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = []
        if not isinstance(tags, list):
            tags = []
        last_used = to_tz_datetime(data.get("last_used"))
        rows.append({
            "skill": data.get("skill") or "",
            "elo": float(data.get("elo") or 1000.0),
            "wins": int(data.get("wins") or 0),
            "losses": int(data.get("losses") or 0),
            "draws": int(data.get("draws") or 0),
            "uses": int(data.get("uses") or 0),
            "success_rate": float(data.get("success_rate") or 0.0),
            "tier": data.get("tier"),
            "tags": tags,
            "last_used": last_used,
        })
    if rows:
        with session_scope() as s:
            for r in rows:
                s.execute(pg_insert(SkillRecord).values(**r).on_conflict_do_nothing(constraint="skills_pkey"))
    return len(rows)


def _migrate_memories(src, report, failed):
    from agent_arena.persistence import session_scope
    from agent_arena.persistence.models import Memory
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    KNOWN = {"user_id", "insight", "tokens", "battle_id", "model_id", "format",
             "chosen_skills", "theory", "outcome", "created_at"}
    rows = []
    for doc in src:
        meta = _doc_meta(doc)
        data = meta["data"]
        docid = meta["id"]
        for f in data.keys():
            if f not in KNOWN:
                report["unknown_fields"].setdefault("memories", {})
                report["unknown_fields"]["memories"][f] = report["unknown_fields"]["memories"].get(f, 0) + 1
        tokens = data.get("tokens")
        if isinstance(tokens, str):
            try:
                tokens = json.loads(tokens)
            except (json.JSONDecodeError, TypeError):
                tokens = []
        if not isinstance(tokens, list):
            tokens = []
        chosen_skills = data.get("chosen_skills")
        if isinstance(chosen_skills, str):
            try:
                chosen_skills = json.loads(chosen_skills)
            except (json.JSONDecodeError, TypeError):
                chosen_skills = []
        if not isinstance(chosen_skills, list):
            chosen_skills = []
        created_at = to_tz_datetime(data.get("created_at")) or to_tz_datetime(meta["createdat"])
        rows.append({
            "id": docid,
            "user_id": data.get("user_id") or "",
            "insight": data.get("insight") or "",
            "tokens": tokens,
            "battle_id": data.get("battle_id"),
            "model_id": data.get("model_id"),
            "format": data.get("format"),
            "chosen_skills": chosen_skills,
            "theory": data.get("theory"),
            "outcome": data.get("outcome"),
            "created_at": created_at,
        })
    if rows:
        with session_scope() as s:
            for r in rows:
                s.execute(pg_insert(Memory).values(**r).on_conflict_do_nothing(constraint="memories_pkey"))
    return len(rows)


if __name__ == "__main__":
    sys.exit(main())
