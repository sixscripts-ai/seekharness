# Authentication Gate

Builder must implement a local FastAPI service in `app.py` with:

- `POST /login` accepting `username` and `password`.
- `GET /admin` requiring a valid bearer token issued by a successful admin login.
- Invalid or forged tokens must return 401/403.

Breaker receives only the frozen `app.py` artifact and may write `exploit.py` to demonstrate a local bypass. No network access is required.
