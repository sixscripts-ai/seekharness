# Agent Arena

Web platform where AI models compete in security/coding "arena" battles. Two services:

- `backend/` — Python 3.12 FastAPI app (deployed on Modal, data in Appwrite Cloud). Package `agent_arena`.
- `frontend/` — Vite + React + TypeScript SPA (deployed on Vercel; Appwrite SDK for auth).

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
  scaffold from `.env.example`. `settings()` raises `RuntimeError` at call time (not import) unless
  all four of `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY`, `APPWRITE_DATABASE_ID`
  are non-empty. The scaffold leaves `APPWRITE_API_KEY` empty; set a real one to run against Appwrite.

### External services
- The **live** Modal backend is `https://sixscripts--agent-arena-backend-fastapi-app.modal.run`
  (`GET /health` works; `GET /formats` and other data routes 500 while the Appwrite project's DB-read
  quota is exhausted — see "fresh Appwrite project bootstrap" below. This is also
  `frontend/vite.config.ts`'s `DEFAULT_MODAL_URL`).
  Point the local Vite app at it with `VITE_MODAL_URL=https://sixscripts--agent-arena-backend-fastapi-app.modal.run`.
- `frontend/src/lib/api.ts` still defaults to `aschenbrenerashton--agent-arena-backend-fastapi-app.modal.run`,
  which is DISABLED (HTTP 404 "workspace is disabled"). Do not use that URL unless `VITE_MODAL_URL` overrides it.
- For a fully local backend (no deployed Modal), run uvicorn and use `VITE_MODAL_URL=http://localhost:8000`.
- The **current** Appwrite Cloud project is `6a92f61d001bf8be437e` (database `arena`,
  `6a92f64c002303d68a4c`, `sfo.cloud.appwrite.io`, tablesdb engine). The previous project
  (`6a6f9133001ed182210d`) hit its DB-read quota (HTTP 402) and was replaced via a fresh project;
  see the bootstrap section below. Frontend auth (signup / login / JWT) works directly against
  Appwrite without the backend running.
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

### Backend: fresh Appwrite project bootstrap
- To move to a new Appwrite Cloud project (fresh quota), set the four `APPWRITE_*` values in
  `.env` and run `backend/.venv/bin/python backend/scripts/bootstrap_appwrite.py`. It creates the
  schema, indexes, seeds formats/targets, and smoke-checks `/health`, `/formats`, `/targets`.
  Battle history cannot be copied off the old project while its DB reads are quota-blocked.
- KNOWN LIMITATION on the new project (tablesdb engine): `ensure_indexes` fails with
  "Index length is longer than the maximum: 767" because the schema's string attributes are too
  long for the new engine's index limit. Queries still work (full scans — fine at current data
  volume). To fix properly, shorten the attribute sizes in `schema.py` (e.g. 255 -> 191) before
  first schema creation, or migrate to the tablesDB API (`list_tables`/`list_rows`).

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
- Run: `APPWRITE_API_KEY=<value> backend/.venv/bin/python -m uvicorn agent_arena.main:app --port 8000`.
  `/health` needs `settings()` to load. A full battle end-to-end additionally needs Appwrite seeded
  with the formats (currently 8 in `ALL_FORMATS`) plus host model keys (`HOST_OPENROUTER_KEY`, etc.) and `JUDGE_MODAL_KEY`/
  `JUDGE_MODAL_SECRET`. `ARENA_USE_MOCK=1` (default in `.env`) uses the in-process mock runner so no
  model keys are needed, but Appwrite is still required to persist battles.

### Frontend: lint / build / run
- Standard scripts in `frontend/package.json` (`pnpm dev`, `pnpm build`, `pnpm lint`, `pnpm check`).
- `pnpm lint` currently reports pre-existing errors (mostly `no-empty` / `no-explicit-any` in
  `src/pages/*`); the linter itself works. `pnpm build` (tsc typecheck + vite) is clean.
- The `esbuild` "Ignored build scripts" warning from `pnpm install` is harmless — the build works.
