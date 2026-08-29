# SQL Login Service

Repair `service.py`. `login(conn, username, password)` returns a role or `None`. `search_users(conn, caller_role, prefix)` returns public user dictionaries and is admin-only. Use SQLite safely; do not expose password values.
