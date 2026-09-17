# SeekHarness — Backend Policy (`backend/`)

> Scoped instructions for FastAPI service, runtime executors, and persistence layer.
> Inherits the canonical engineering mission and product invariants from
> [`../AGENTS.md`](../AGENTS.md). These are component policies, not agent ownership
> restrictions: either AG or Codex may implement work here for an assigned task.

---

## 1. Persistence & Transaction Integrity

- **Neon PostgreSQL is System of Record**: All Battles, Formats, Events, Official Results, and Elo ratings persist authoritatively to Neon.
- **Appwrite Boundary**: Appwrite is used solely for JWT identity validation (`Account.get()`). Never persist battle records or stats to Appwrite Documents/TablesDB. `APPWRITE_DUAL_WRITE` and `APPWRITE_READ_FALLBACK` must remain `false`.
- **Idempotency & Concurrency**: Finalization updates, battle state transitions, and rating adjustments must use transaction-safe atomic operations or idempotency keys to prevent duplicate scoring or split-brain states.

---

## 2. Fighter Sandbox Isolation & Fail-Closed Boundaries

- **Fighter SQL Access**:
  - A Fighter sandbox may receive ONLY battle-scoped, ephemeral database credentials provisioned for that specific battle instance.
  - If battle-scoped credentials are unavailable or unconfigured, database operations must **fail closed with an explicit error**.
  - **NEVER fall back to control-plane `DATABASE_URL`** under any circumstance.
- **Fighter HTTP & Network Egress**:
  - Fighter network access is deny-by-default.
  - Only destinations explicitly authorized by the validated Target/Format/Battle policy may be reached.
  - Battle-local services (such as mock web apps or internal APIs) may be reachable only when intentionally provisioned and allowlisted for that Battle.
  - SSRF defenses must unconditionally reject Arena control-plane infrastructure, cloud metadata services (`169.254.169.254`), unauthorized internal services, and credential-bearing management endpoints. Redirects and alternate-address forms must not bypass policy.
- **Credential Stripping**:
  - Cleanse host environment variables before initializing Fighter sandboxes. Host API keys, database connection strings, Appwrite server secrets, and Modal tokens must never enter the Fighter process environment. Credentials must never be forwarded to untrusted destinations.

---

## 3. Provider Integrity & Failure Classification

- **Provenance Recording**: Every model invocation must capture canonical provider identity, exact model string, latency, token counts, and completion status.
- **Infrastructure vs. Fighter Failure Separation**:
  - Provider infrastructure failures (missing API credentials, HTTP 429 rate limits, HTTP 502/503/504 gateways, timeouts, context overflows, network disconnects, or no-first-token stream aborts) **must NEVER silently become Fighter losses or Breaker victories**.
  - Classify infrastructure, provider, sandbox-boot, and no-first-token failures with the repository's current failure taxonomy, distinctly from Fighter losses, to preserve Elo integrity.

---

## 4. Trusted Verifier & Finalization Contracts

- **Trusted Target Verifier**:
  - Verifier commands (`visible_command`, `hidden_command`) execute under `agent_arena.target_verifier` with strict command guards (`_command_guard.py`).
  - Verifier execution must occur inside the isolated sandbox environment; `ARENA_VERIFIER_ALLOW_INPROCESS=1` is reserved strictly for hermetic unit tests and must be disabled in production.
- **Fail-Closed Finalization**:
  - Finalization must fail closed if required verification artifacts, evidence bundles, or evaluator outputs are missing, corrupt, or contradictory.
  - Judge output provides qualitative narrative only; it cannot override deterministic ground-truth verification assertions.
- **Authoritative Persistence**:
- Only the trusted backend finalizer may transition a Battle to its authoritative completed result.
