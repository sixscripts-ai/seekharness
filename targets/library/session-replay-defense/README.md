# Session Replay Defense

Implement `issue(user, now, ttl=30)` and `verify(token, now)` in `tokens.py`. Tokens must be authenticated, expire after TTL, and be accepted only once. A successful verify returns the username; invalid/replayed tokens raise `ValueError`.
