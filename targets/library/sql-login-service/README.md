# SQL Login Service

Repair `service.py`. `login(conn, username, password)` returns a role or `None`. `search_users(conn, caller_role, prefix)` returns public user dictionaries and is admin-only. Use SQLite safely; do not expose password values.

Breakers submit `exploit.py`. It may inspect and exercise the public `service.py`, then print one JSON attack request for the verifier to run against a fresh database:

- Login bypass: `{"operation":"login","username":"...","password":"..."}`
- User search: `{"operation":"search","caller_role":"user","prefix":"..."}` (or use `"admin"` to test password disclosure)

The verifier checks the service's actual return value and database-backed data. Text claiming success does not count.
