from . import db

# Collection id -> [(attribute, type, required)]
# types: string | integer | float | boolean ; arrays use attribute_key="__array"
COLLECTIONS = {
    "providers": [
        ("user_id", "string", True),
        ("name", "string", True),
        ("base_url", "string", True),
        ("encrypted_key", "string", True),
        ("masked_key", "string", True),
        ("auth_style", "string", True),
        (
            "model_name",
            "string",
            False,
        ),  # optional for existing docs; required on API create
    ],
    "formats": [
        ("name", "string", True),
        ("engine", "string", True),
        ("config", "string", True),
    ],
    "battles": [
        ("user_id", "string", True),
        ("format_id", "string", True),
        ("model_ids", "string", True),  # __array variant
        ("arena_size", "integer", True),
        ("status", "string", True),
        ("timeout_seconds", "integer", True),
        ("round_visibility", "string", True),
        ("saved", "boolean", True),
        ("sandbox_id", "string", False),
        ("judge_provider_id", "string", False),
        ("preview_urls", "string", False),  # JSON map model_id -> tunnel URL
        ("failure_reason", "string", False),
        ("started_at", "float", False),
        ("difficulty", "string", False),
    ],
    "battle_events": [
        ("battle_id", "string", True),
        ("event_id", "string", True),
        ("payload", "string", True),
        ("created_at", "float", True),
    ],
    "rounds": [
        ("battle_id", "string", True),
        ("phase", "string", True),
        ("model_id", "string", True),
        ("artifact", "string", True),
    ],
    "scores": [
        ("battle_id", "string", True),
        ("model_id", "string", True),
        ("score", "float", True),
        ("judge_model", "string", True),
        ("justification", "string", False),
    ],
    "leaderboard": [
        ("model_id", "string", True),
        ("format_id", "string", True),
        ("elo", "float", True),
        ("games_played", "integer", True),
    ],
    "skills": [
        ("skill", "string", True),
        ("elo", "float", True),
        ("wins", "integer", True),
        ("losses", "integer", True),
        ("draws", "integer", True),
        ("uses", "integer", True),
        ("success_rate", "float", True),
        ("tier", "string", True),
        ("tags", "string", False),  # array variant
        ("last_used", "float", True),
    ],
    "memories": [
        ("user_id", "string", True),
        ("insight", "string", True),
        ("tokens", "string", False),  # array variant
        ("battle_id", "string", True),
        ("model_id", "string", False),
        ("format", "string", False),
        ("chosen_skills", "string", False),  # array variant
        ("theory", "string", False),
        ("outcome", "string", False),
        ("created_at", "float", True),
    ],
    "targets": [
        ("id", "string", True),
        ("config", "string", True),
    ],
}

ARRAY_ATTRIBUTES = {
    "battles": {"model_ids": 256},
    "skills": {"tags": 64},
    "memories": {"tokens": 512, "chosen_skills": 64},
}

TEARDOWN_COLLECTIONS = list(COLLECTIONS)


def _create_collection_if_missing(databases, database_id, collection_id, spec):
    res = databases.list_collections(database_id)
    existing = {c.id for c in res.collections}
    if collection_id not in existing:
        databases.create_collection(
            database_id, collection_id, collection_id, permissions=[]
        )


def _create_attribute(databases, database_id, collection_id, name, type_, required):
    if type_ == "string":
        databases.create_string_attribute(
            database_id, collection_id, name, 262144, required=required
        )
    elif type_ == "integer":
        databases.create_integer_attribute(
            database_id, collection_id, name, required=required
        )
    elif type_ == "float":
        databases.create_float_attribute(
            database_id, collection_id, name, required=required
        )
    elif type_ == "boolean":
        databases.create_boolean_attribute(
            database_id, collection_id, name, required=required
        )


def ensure_schema() -> None:
    databases = db.get_databases()
    database_id = db.get_database_id()
    for collection_id, attrs in COLLECTIONS.items():
        _create_collection_if_missing(databases, database_id, collection_id, attrs)
        res = databases.list_attributes(database_id, collection_id)
        existing = {a.key for a in res.attributes}
        for name, type_, required in attrs:
            if name in existing:
                continue
            array_size = ARRAY_ATTRIBUTES.get(collection_id, {}).get(name)
            if array_size:
                databases.create_string_attribute(
                    database_id,
                    collection_id,
                    name,
                    array_size,
                    required=required,
                    array=True,
                )
            else:
                _create_attribute(
                    databases, database_id, collection_id, name, type_, required
                )
