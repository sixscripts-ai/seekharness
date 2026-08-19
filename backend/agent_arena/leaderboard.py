from appwrite.query import Query

from . import elo


def _find_entry(databases, database_id, model_id, format_id):
    res = databases.list_documents(
        database_id, "leaderboard",
        queries=[
            Query.equal("model_id", model_id),
            Query.equal("format_id", format_id),
            Query.limit(1),
        ],
    )
    docs = res.documents
    return docs[0] if docs else None


def _load_elo(databases, database_id, model_id, format_id) -> float:
    entry = _find_entry(databases, database_id, model_id, format_id)
    return entry.data["elo"] if entry else elo.INITIAL_RATING


def _upsert(databases, database_id, model_id, format_id, new_elo) -> None:
    entry = _find_entry(databases, database_id, model_id, format_id)
    if entry:
        databases.update_document(database_id, "leaderboard", entry.id, {
            "elo": new_elo,
            "games_played": entry.data["games_played"] + 1,
        })
    else:
        databases.create_document(database_id, "leaderboard", "unique()", {
            "model_id": model_id,
            "format_id": format_id,
            "elo": new_elo,
            "games_played": 1,
        })


def apply_result(databases, database_id, format_id, model_ids, scores) -> None:
    scopes = [format_id]
    if format_id != "overall":
        scopes.append("overall")
    for scope in scopes:
        for i in range(len(model_ids)):
            for j in range(i + 1, len(model_ids)):
                a, b = model_ids[i], model_ids[j]
                sa, sb = scores[a], scores[b]
                ra = _load_elo(databases, database_id, a, scope)
                rb = _load_elo(databases, database_id, b, scope)
                outcome_a = 1.0 if sa > sb else (0.0 if sa < sb else 0.5)
                new_a, new_b = elo.update_ratings(ra, rb, outcome_a)
                _upsert(databases, database_id, a, scope, new_a)
                _upsert(databases, database_id, b, scope, new_b)


def get_rankings(databases, database_id, format_id="overall") -> list[dict]:
    page = 100
    offset = 0
    docs = []
    while True:
        res = databases.list_documents(
            database_id,
            "leaderboard",
            queries=[
                Query.equal("format_id", format_id),
                Query.limit(page),
                Query.offset(offset),
            ],
        )
        batch = list(res.documents)
        docs.extend(batch)
        if len(batch) < page:
            break
        offset += page
        if offset > 10000:
            break
    entries = sorted(docs, key=lambda e: e.data["elo"], reverse=True)
    return [
        {"model_id": e.data["model_id"], "elo": e.data["elo"], "games_played": e.data["games_played"], "rank": i + 1}
        for i, e in enumerate(entries)
    ]
