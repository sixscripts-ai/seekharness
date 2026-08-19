# Deployment & Environment Variables — Agent Arena (seekharness)

This documents how the two services are deployed and every environment
variable they need. **Do not commit real secrets to the repo** — set them in
the Vercel / Modal dashboards.

## Services

| Service | Host | Public URL |
|---|---|---|
| Frontend (Vite SPA) | Vercel | `https://seekharness.vercel.app` |
| Backend (FastAPI) | Modal | `https://sixscripts--agent-arena-backend-fastapi-app.modal.run` |
| Data | Appwrite Cloud | `https://sfo.cloud.appwrite.io/v1` |

---

## 1. Frontend (Vercel)

### Root Directory (required — the app is in `frontend/`)

This is a monorepo: the buildable app lives in `frontend/`, not the repo root.
In the Vercel project settings, set:

- **Root Directory**: `frontend`
- **Build Command**: `pnpm build`
- **Output Directory**: `dist`
- **Install Command**: `pnpm install`

If Root Directory is left blank, Vercel looks at the repo root (which has no
`package.json`) and the deploy fails with a 404. This is the cause of the
"NOT_FOUND" on a fresh project.

### Environment variables (Vercel `frontend` project)

None of these are secrets; they are build-time config with safe fallbacks
already baked into the code.

| Variable | Required | Notes |
|---|---|---|
| `VITE_MODAL_URL` | No | Backend base URL. Defaults to `https://sixscripts--agent-arena-backend-fastapi-app.modal.run`. |
| `VITE_APPWRITE_ENDPOINT` | No | Appwrite API endpoint. Defaults to `https://sfo.cloud.appwrite.io/v1`. |
| `VITE_APPWRITE_PROJECT_ID` | No | Appwrite project id. Defaults to `6a6f9133001ed182210d`. |

> The Appwrite **project id** is public (it ships in the client SDK by
> design). The Appwrite API *key* is NOT used by the frontend — it stays
> server-side on the backend.

---

## 2. Backend (Modal)

All of the following are set as **Modal secrets** on the backend app. Secrets
must be rotated if they were ever shared in chat/logs.

### Required (backend won't start without these four)

| Variable | Notes |
|---|---|
| `APPWRITE_ENDPOINT` | `https://sfo.cloud.appwrite.io/v1` |
| `APPWRITE_PROJECT_ID` | Appwrite project id |
| `APPWRITE_API_KEY` | **Secret.** Server API key with DB access. Rotate if exposed. |
| `APPWRITE_DATABASE_ID` | Appwrite database id |

### Encryption & internal auth

| Variable | Notes |
|---|---|
| `FERNET_KEY` | **Secret.** Active key encrypting user provider keys. |
| `FERNET_KEY_OLD` | **Secret.** Comma-separated retired keys (only needed on rotation). Leave empty on first deploy. |
| `INTERNAL_API_KEY` | **Secret.** Master signing key for sandbox tokens. **Highest priority to rotate if exposed.** Only lives on the backend; sandboxes now receive a derived per-battle token, never this key. |

### Judge (host Kimi-K3 on Modal)

| Variable | Notes |
|---|---|
| `JUDGE_MODAL_KEY` | **Secret.** Modal WebSocket key. |
| `JUDGE_MODAL_SECRET` | **Secret.** Modal WebSocket secret. |
| `JUDGE_MODAL_BASE` | `https://inference.us-west.modal.direct/v1` |
| `JUDGE_MODAL_MODEL` | `sixscripts--ep-kimi-k3-server.us-west.modal.direct` |

### Host model providers (each is a **secret** API key)

Only set the ones you want exposed in `GET /providers`; the code omits any
host whose key is missing.

| Variable | Provider |
|---|---|
| `HOST_OPENROUTER_KEY` | OpenRouter (free tier defaults) |
| `HOST_OPENCODE_GO_KEY` | OpenCode Go (DeepSeek V4 Flash) |
| `HOST_GROQ_KEY` | Groq |
| `HOST_XAI_KEY` | xAI |
| `HOST_DEEPSEEK_KEY` | DeepSeek |
| `HOST_OPENAI_KEY` | OpenAI |
| `HOST_META_KEY` | Meta |
| `HOST_MERGE_KEY` | Merge Gateway |
| `HOST_TOKENROUTER_KEY` | TokenRouter |
| `HOST_MANUS_KEY` | Manus |

### Runtime flags / non-secrets

| Variable | Notes |
|---|---|
| `BACKEND_PUBLIC_URL` | Public backend URL sandboxes call back to. |
| `ARENA_USE_MODAL_SANDBOX` | `"1"` enables Modal Sandbox spawn on battle create. |
| `ARENA_USE_MOCK` | `"1"` uses the in-process mock runner (tests). |
| `SANDBOX_TIMEOUT` | Max seconds a spawned sandbox may live (default 900). |
| `REAPER_GRACE_SECONDS` | Grace past battle timeout before reaper fails it (default 300). |
| `ARENA_ADMIN_USER_IDS` | Comma-separated admin user ids. |

---

## 3. CORS allowlist (backend)

`backend/agent_arena/main.py` restricts cross-origin access to:

- `https://seekharness.vercel.app` (current production)
- `https://agent-arena-blond.vercel.app` (legacy)
- `https://frontend-seven-snowy-59.vercel.app` (legacy)
- `http://localhost:3000` / `http://localhost:3010` (dev)

**If you change the Vercel domain, update this list** or the new origin will
be blocked from calling the API.

---

## 4. Key rotation procedure

When rotating any secret (especially `INTERNAL_API_KEY`, `FERNET_KEY`,
`APPWRITE_API_KEY`), follow this order to avoid bricking live data:

1. Add the old value to `FERNET_KEY_OLD` (comma-separated) and set the new
   value to `FERNET_KEY`. Deploy. New writes use the new key; old ciphertexts
   still decrypt via the old key.
2. Rotate `INTERNAL_API_KEY`. Sandboxes receive short-lived tokens signed by
   this key, so rotating it only invalidates in-flight sandboxes (they'll be
   reaped), never stored data.
3. Rotate `APPWRITE_API_KEY` last (it gates all DB access).

Rotate `HOST_*` / `JUDGE_*` keys at the provider directly; they only affect
outbound model calls and have no stored-ciphertext dependency.
