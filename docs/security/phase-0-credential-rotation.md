# Phase 0 - Credential Rotation Checklist

Status: **PENDING HUMAN ACTION** (do not block engineering on this).

Anything that ever lived in git or in shared docs is treated as compromised,
regardless of whether it was actually abused. Rotate in this order so live
data never becomes unreadable:

## 1. Modal workspace tokens (highest urgency)
- AGENTS.md records that Modal CLI tokens lived in git history (`.kilo/kilo.json`
  on older commits) and were recovered from it.
- In the Modal dashboard: revoke the affected API tokens for BOTH workspaces
  (`sixscripts` - the live deployment - and the spend-capped
  `aschenbrenerashton`). Create fresh tokens with minimal scope (deploy only).
- Replace `~/.modal.toml` on every machine and any CI/GitHub secrets that carry
  them.
- Redeploy the live app once with the new token to confirm the workspace
  accepts it.

## 2. JUDGE_MODAL_KEY / JUDGE_MODAL_SECRET
- Also recovered from git history per AGENTS.md. Rotate at the Modal inference
  endpoint that serves Kimi-K3 (sixscripts--ep-kimi-k3-server).
- Set the new values as Modal secrets on the backend app; redeploy; verify a
  battle judge call returns scores.

## 3. INTERNAL_API_KEY
- Generate: `openssl rand -hex 32`.
- Set as Modal secret on the backend app + local `.env`.
- Rotating only invalidates in-flight sandbox tokens (they are reaped), never
  stored data.

## 4. APPWRITE_API_KEY
- In Appwrite console: create a new server API key with the same scopes
  (databases read/write on the arena database).
- Set as Modal secret + local `.env`; verify `GET /health` and `/formats`.
- Revoke the old key last - it gates all DB access.

## 5. FERNET_KEY (only if suspect)
- Encrypts stored user provider keys. Follow docs/deployment-env-vars.md:
  put the old value in `FERNET_KEY_OLD` (comma-separated), set `FERNET_KEY` to
  the new key, deploy, then after a soak period remove the old entry.

## 6. HOST_* provider keys
- Rotate at each provider (OpenRouter, Groq, xAI, DeepSeek, OpenAI, Meta,
  Merge, TokenRouter, Manus, OpenCode Go) only for keys that ever appeared in
  chat, logs, or docs.

## 7. Vercel / GitHub
- `.vercel/` and CI secrets: confirm no historical token was committed;
  rotate Vercel tokens if any were.

## 8. Verification
- `grep -R -i "api_key\|secret\|token" --exclude-dir=.git .` in the repo and
  confirm no live values remain in tracked files.
- Confirm `.env` stays gitignored.
- After rotation: run one live battle end-to-end and confirm judge + Elo +
  evidence events still flow.

Code-level mitigation already landed (commit e6a538c): `_strip_secret_env()`
scrubs `*_KEY`, `*_SECRET`, `*_TOKEN`, `*_PASSWORD` plus exact
`FERNET_KEY`/`INTERNAL_API_KEY`/`BATTLE_TOKEN` from every toolbelt child
process, with regression tests in `backend/tests/test_advanced_executor.py`.
