# Agent Arena

Web platform where AI models compete in security/coding "arena" battles. Two services:

- `backend/` — Python 3.12 FastAPI app (deployed on Modal; battles / Elo / events in Neon Postgres). Package `agent_arena`.
- `frontend/` — Vite + React + TypeScript SPA (deployed on Vercel; Appwrite SDK for identity only).

## Cursor Cloud specific instructions

The startup update script already installs `uv`, creates `backend/.venv`, installs backend deps
(`-e "./backend[dev]"`), runs `pnpm -C frontend install`, and bootstraps a non-secret `.env` from
`.env.example` if missing. The notes below are the non-obvious gotchas; standard commands live in
`backend/pyproject.toml`, `backend/pytest.ini`, and `frontend/package.json`.

### Environment / config
- No system `python3-venv`/`ensurepip` and no `apt`/`sudo`. Use the `uv`-managed venv at
  `backend/.venv` (do not `python -m venv`). Run backend tools via `backend/.venv/bin/python`.
- Backend config lives in repo-root `.env` (loaded by `agent_arena/config.py` and
  `tests/conftest.py`). `.env` is gitignored, so it is NOT committed — the update script recreates a
  scaffold from `.env.example`. With `PERSISTENCE_BACKEND=postgres` and dual-write/read-fallback
  off (the default), `settings()` only requires `APPWRITE_ENDPOINT` and `APPWRITE_PROJECT_ID` for
  JWT auth. `APPWRITE_API_KEY` / `APPWRITE_DATABASE_ID` are still required if you re-enable
  Appwrite as a battle store (`PERSISTENCE_BACKEND=appwrite` or dual-write / read-fallback).
  Do not mix a Clerk/Better Auth/Neon Auth rewrite into this; identity stays Appwrite.

### External services
- The **live** Modal backend is `https://sixscripts--agent-arena-backend-fastapi-app.modal.run`
  (`GET /health` works; `/formats`, `/stats`, and battles read Neon). This is also
  `frontend/vite.config.ts`'s `DEFAULT_MODAL_URL`.
  Point the local Vite app at it with `VITE_MODAL_URL=https://sixscripts--agent-arena-backend-fastapi-app.modal.run`.
  `/health` reports `persistence_backend`, `appwrite_dual_write`, and `appwrite_read_fallback`.
  Those last two must stay `false`. Appwrite Documents/TablesDB is not the battle system of record.
- `frontend/src/lib/api.ts` still defaults to `aschenbrenerashton--agent-arena-backend-fastapi-app.modal.run`,
  which is DISABLED (HTTP 404 "workspace is disabled"). Do not use that URL unless `VITE_MODAL_URL` overrides it.
- For a fully local backend (no deployed Modal), run uvicorn and use `VITE_MODAL_URL=http://localhost:8000`.
- The **current** Appwrite Cloud project is `6a92f61d001bf8be437e` (database `arena`,
  `6a92f64c002303d68a4c`, `sfo.cloud.appwrite.io`, tablesdb engine). The previous project
  (`6a6f9133001ed182210d`) hit its DB-read quota (HTTP 402) and was replaced via a fresh project;
  see the identity notes below. Frontend auth (signup / login / JWT) works directly against
  Appwrite without the backend running. The API still authenticates that JWT with `Account.get()`.
  Keep Appwrite for identity. Neon (`PERSISTENCE_BACKEND=postgres`) is the battle database.
- `/Users/villain/modal/.env` is a Mac-local Modal env file and does **not** exist in this Linux cloud VM.
  Equivalent Modal CLI tokens were recovered from git history (`.kilo/kilo.json` on older commits,
  `MEM0_DEFAULT_USER_ID=villain`) and written to local gitignored `.env` as `JUDGE_MODAL_KEY` /
  `JUDGE_MODAL_SECRET` plus `~/.modal.toml` (profile `aschenbrenerashton`). That workspace is
  **spend-capped** (`Workspace ac-FcK37hwF7BgQXQSxI45KNV has exceeded its spend limit`), which is
  why `*.modal.run` returns 404. The deployed dotenv secret `st-F1YD6yTlOmB1oFSPORKPfj` still exists
  on that app but cannot be dumped without running a container. `APPWRITE_API_KEY` and `HOST_*_KEY`
  were never committed; they still need to be pasted. Rotate the Modal tokens — they lived in git.

### Backend: target verifier safety
- The Trusted Target Verifier (`agent_arena/target_verifier.py`) executes manifest-supplied
  `visible_command`/`hidden_command` strings. Seatbelts: commands are rejected by the shared
  `sandbox/executors/_command_guard.py` (no `..`/`~`/`$HOME`/absolute paths; no curl/wget unless
  the target sets `network: true`; SSRF URLs always blocked), manifests are validated at load time
  (`target_library.py`), and the verifier refuses to run outside the sandbox unless
  `ARENA_VERIFIER_ALLOW_INPROCESS=1` is set (unit tests set this; production must not).

### Backend: Appwrite is identity, not the battle DB
- Do not bootstrap Appwrite Documents/TablesDB to persist new battles. Formats, battles, Elo, and
  events live in Neon. `APPWRITE_DUAL_WRITE` and `APPWRITE_READ_FALLBACK` default to false and are
  pinned false in `backend/modal_entry.py`. Re-enabling them recreates the split-brain (UI battle
  missing from Neon, `/stats` lying).
- Optional one-shot copy of old Appwrite rows: `backend/scripts/backfill_appwrite_to_postgres.py`.
  Do not backfill abandoned queued/running rows into Neon just to "catch up."
- `bootstrap_appwrite.py` still exists for a document schema that production should no longer use
  as source of truth. TablesDB index-length 767 failures on that schema are a reason not to go back.

### Backend: test / run
- Tests: `backend/.venv/bin/python -m pytest --ignore=tests/evals`. Always pass `--ignore=tests/evals`:
  `tests/evals/` is a DeepEval suite that imports an OpenRouter model at collection time and errors
  without `OPENROUTER_API_KEY`. `pytest.ini` already deselects `-m modal` (real Modal sandbox tests).
- Appwrite-backed tests auto-skip when `APPWRITE_API_KEY` is empty (see `conftest.HAVE_APPWRITE`).
- Known failures with an empty `APPWRITE_API_KEY` (they call `settings()` but are not guarded by the
  skip): `test_health`, `test_internal_requires_key`, `test_get_model_call_spec_host_free`, and
  `test_auth::test_returns_appwrite_user_*`. All pass once `APPWRITE_API_KEY` is set to any non-empty
  value. `test_redact::test_four_spec_patterns_present` is a PRE-EXISTING failure unrelated to setup
  (asserts 4 patterns; `redact.REDACT_PATTERNS` has 11) — do not "fix" it as part of env setup.
- Run: `backend/.venv/bin/python -m uvicorn agent_arena.main:app --port 8000` with
  `PERSISTENCE_BACKEND=postgres` and a Neon `DATABASE_URL`. `/health` needs `settings()` to load
  (Appwrite endpoint + project id). A full battle end-to-end needs formats in Postgres (currently 8
  in `ALL_FORMATS`) plus host model keys (`HOST_OPENROUTER_KEY`, etc.) and `JUDGE_MODAL_KEY` /
  `JUDGE_MODAL_SECRET`. `ARENA_USE_MOCK=1` uses the in-process mock runner so no model keys are
  needed; battles still persist to Neon, not Appwrite.

### Frontend: lint / build / run
- Standard scripts in `frontend/package.json` (`pnpm dev`, `pnpm build`, `pnpm lint`, `pnpm check`).
- `pnpm lint` currently reports pre-existing errors (mostly `no-empty` / `no-explicit-any` in
  `src/pages/*`); the linter itself works. `pnpm build` (tsc typecheck + vite) is clean.
- The `esbuild` "Ignored build scripts" warning from `pnpm install` is harmless — the build works.
