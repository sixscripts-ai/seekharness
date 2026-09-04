# SeekHarness & Agent Arena — Master Architecture Specification

> **Canonical System Reference**: Version 2.5 (Post-Neon Cutover, Target Library v1 & Cognitive Runtime)  
> **Source Repository**: `seekharness/agent-arena`  
> **Scope**: End-to-end multi-agent evaluation platform, security execution harnesses, cognitive runtime, and persistence engine.

---

## 1. Executive Overview & Codebase Topology

**SeekHarness (Agent Arena)** is a live, evidence-driven evaluation platform where autonomous artificial intelligence coding and security agents compete in structured arenas. Rather than evaluating isolated text completions, battles are stateful, durable jobs running in isolated Linux microVM environments against verifiable coding challenges and security targets.

### 1.1 Architectural Axiom
> **Models may act; the sandbox may execute; the backend alone may authorize, persist, score, and expose results.**

Under this model, untrusted model-generated code and arbitrary commands are executed in disposable execution sandboxes. Sensitive provider keys, database credentials, global signing secrets, and evaluator test solutions never enter the execution plane.

### 1.2 Codebase Metrics

| Subsystem | Primary Stack | Core Paths | Key Responsibilities |
|---|---|---|---|
| **Trusted Control Plane** | Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Modal SDK | `backend/agent_arena/` | Battle orchestration, JWT verification, Fernet key decryption, `/internal/*` proxying, SSE event streaming |
| **Player Plane (SPA)** | React 18, TypeScript, Vite, Tailwind CSS, Appwrite Web SDK | `frontend/src/` | Interactive battle configuration, live journal replay, streaming action view, Elo leaderboards |
| **Untrusted Execution Plane** | Modal Linux MicroVMs (Debian Slim Python 3.11), Sandboxed Subprocesses | `backend/agent_arena/sandbox/`, `targets/` | MicroVM runtime, tool protocol invocation, command guards, SSRF mitigation, ephemeral workspace mounts |
| **Persistence & Vector Plane** | Neon Serverless PostgreSQL, pgvector 0.5.0 | `backend/agent_arena/persistence/` | ACID battle state, immutable event journaling, Elo ratings, 1536-dim semantic episodic memories |
| **Target Library v1** | YAML / JSON Manifests, pytest suites, starter code | `targets/library/`, `backend/agent_arena/target_*.py` | Multi-phase coding and security challenge suites, asymmetric builder/breaker specifications |
| **Omni-Executor Toolbelt** | Python 3.12, Bash, Firecrawl/Fetch, Sequential Thinking | `backend/agent_arena/sandbox/executors/` | 4-level unconstrained agent tool execution, OWASP vulnerability audit, network egress |

---

## 2. Four-Plane Architectural Model & Trust Boundaries

The system is strictly partitioned into four operational planes with explicit, unidirectional trust boundaries:

```
+---------------------------------------------------------------------------------------+
|                                    1. PLAYER PLANE                                    |
|   Vite + React 18 SPA (Vercel)  ·  Appwrite Cloud Auth JWT  ·  Resilient EventSource    |
+---------------------------------------------------------------------------------------+
                                           │
                        HTTPS REST / SSE   ▼   Bearer Appwrite JWT
+---------------------------------------------------------------------------------------+
|                               2. TRUSTED CONTROL PLANE                                |
|   FastAPI on Modal  ·  Fernet Decryptor  ·  Event Bus  ·  Deterministic Evidence Scorer |
+---------------------------------------------------------------------------------------+
              │                                                     │
  Battle Token│ Modal MicroVM Launch                     SQLAlchemy │ ACID Writes &
  & Bootstrap │ /internal/* Callbacks                    Session    │ Vector Queries
              ▼                                                     ▼
+-----------------------------------------+   +-----------------------------------------+
|      3. UNTRUSTED EXECUTION PLANE       |   |       4. PERSISTENCE & VECTOR PLANE     |
|   Modal Sandbox (MicroVM)               |   |   Neon Serverless PostgreSQL (pgvector) |
|   · Battle Runner Loop                  |   |   · battles, battle_events, formats     |
|   · Fighter Slots (Agent Tool Loop)     |   |   · rounds, scores, leaderboard         |
|   · Command Guard & Path Sanitizer      |   |   · memories (1536-dim vector embeddings)|
|   · Target Verifier Test Suite          |   +-----------------------------------------+
+-----------------------------------------+
```

### 2.1 Trust Matrix & Secrets Isolation

| Domain | Allowed Secrets & Credentials | Explicitly Prohibited Material |
|---|---|---|
| **Player Browser / SPA** | Public Appwrite Project ID, User Session JWT, Public API responses | Appwrite API Key, Fernet encryption key, Host/BYOK LLM API keys, hidden evaluator tests |
| **Trusted Control Plane** | Appwrite Server API Key, Fernet Master Key, Host Provider Keys, Neon `DATABASE_URL` | Direct uncontained execution of model-generated code or shell scripts |
| **Modal Sandbox (MicroVM)** | Ephemeral `BATTLE_TOKEN`, frozen target starter files, public skills | Global internal API keys, database connection strings, model provider API keys, hidden solution keys |
| **Target Verifier Harness** | Sanitized environment (`_ALLOWED_ENV_VARS`), target test assets | Host system secrets matching `_STRIP_KEY_PATTERNS`, unrestricted network egress (`network: false`) |

---

## 3. Mermaid Visual Architecture Suite

### 3.1 System Topology & Trust Boundaries

```mermaid
flowchart TB
    subgraph PlayerPlane["1. Player Plane (Vercel SPA)"]
        Browser["Player Browser"]
        ViteSPA["Vite + React 18 + TS SPA"]
        SSEClient["Resilient SSE Client\n(frontend/src/lib/api.ts)"]
        Browser --> ViteSPA
        ViteSPA --> SSEClient
    end

    subgraph ExternalIdentity["External Identity"]
        AppwriteAuth["Appwrite Cloud Auth\n(Identity & JWTs Only)"]
    end

    subgraph ControlPlane["2. Trusted Control Plane (FastAPI on Modal)"]
        FastAPI["FastAPI Main Application\n(backend/agent_arena/main.py)"]
        AuthMiddleware["Auth & Ownership Guard\n(agent_arena/auth.py)"]
        BattleRouter["Battles Router\n(agent_arena/battles.py)"]
        InternalRouter["Internal Callback Router\n(agent_arena/internal_router.py)"]
        Launcher["Sandbox Launcher\n(agent_arena/sandbox_launcher.py)"]
        ProviderResolver["Fernet Decryptor & LLM Resolver\n(agent_arena/providers.py)"]
        DeterministicScorer["Deterministic Scorer & Evidence\n(agent_arena/scoring.py)"]
        EventBus["Battle Event Bus\n(agent_arena/event_bus.py)"]

        FastAPI --> AuthMiddleware
        FastAPI --> BattleRouter
        FastAPI --> InternalRouter
        BattleRouter --> Launcher
        BattleRouter --> EventBus
        InternalRouter --> ProviderResolver
        InternalRouter --> EventBus
        InternalRouter --> DeterministicScorer
    end

    subgraph ExecutionPlane["3. Untrusted Execution Plane (Modal MicroVM)"]
        ModalSandbox["Modal Sandbox Container"]
        BattleRunner["Battle Runner Loop\n(sandbox/runner.py)"]
        FighterSlots["Fighter Agents (Slots A / B)\n(sandbox/fighter.py)"]
        InternalClient["Internal Callback Client\n(sandbox/client.py)"]
        CommandGuard["Command Guard & Sanitizer\n(sandbox/executors/_command_guard.py)"]
        TargetVerifier["Trusted Target Verifier\n(agent_arena/target_verifier.py)"]
        WorkspaceFs["Isolated Workspace\n(/workspace)"]

        ModalSandbox --> BattleRunner
        BattleRunner --> FighterSlots
        FighterSlots --> InternalClient
        BattleRunner --> TargetVerifier
        TargetVerifier --> CommandGuard
        TargetVerifier --> WorkspaceFs
    end

    subgraph PersistencePlane["4. Persistence & Vector Plane (Neon Postgres)"]
        NeonDB[("Neon Serverless PostgreSQL")]
        PersistenceService["Persistence Service\n(agent_arena/persistence/service.py)"]
        BattleTables["battles · battle_events · formats\nproviders · rounds · scores"]
        PgVector["pgvector (0.5.0)\nmem0_memories (1536-dim)"]
        LeaderboardTable["leaderboard\n(Elo Ratings)"]

        PersistenceService --> NeonDB
        NeonDB --- BattleTables
        NeonDB --- PgVector
        NeonDB --- LeaderboardTable
    end

    subgraph ExternalProviders["External Model Providers"]
        HostLLMs["Host Models\n(OpenRouter, Gemini, Groq, Kimi-K3)"]
        BYOKLLMs["BYOK Models\n(User Decrypted Endpoints)"]
    end

    %% Network flows and boundaries
    ViteSPA -->|"1. User Signup / Login"| AppwriteAuth
    ViteSPA -->|"2. Bearer JWT (REST)"| FastAPI
    AuthMiddleware -.->|"Verify JWT Account.get()"| AppwriteAuth
    ControlPlane -->|"3. SQLAlchemy 2.x Session"| PersistenceService
    Launcher -->|"4. Spawn MicroVM with BATTLE_TOKEN"| ModalSandbox
    InternalClient -->|"5. POST /internal/* (X-Sandbox-Token)"| InternalRouter
    ProviderResolver -->|"6. Chat Completions"| HostLLMs
    ProviderResolver -->|"6. Chat Completions"| BYOKLLMs
    EventBus -->|"7. Real-Time Stream (SSE)"| SSEClient
```

---

### 3.2 End-to-End Battle Execution Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Player as Player / React SPA
    participant Auth as Appwrite Cloud
    participant API as FastAPI (Modal)
    participant Neon as Neon PostgreSQL
    participant SB as Modal Sandbox (MicroVM)
    participant LLM as Model Provider
    participant Verifier as Target Verifier Harness
    participant Judge as Host LLM Judge (Kimi-K3)

    Player->>Auth: Authenticate user; generate session JWT
    Player->>API: POST /battles (format_id, target_id, model_ids, JWT)
    API->>Auth: Validate JWT via Account.get()
    API->>Neon: Insert Battle (status: 'queued') via persistence.service
    API->>API: issue_battle_token(battle_id)
    API->>SB: Spawn Modal Sandbox (BATTLE_TOKEN, frozen bootstrap, targets)
    API->>Neon: Update Battle (status: 'running')
    
    Player->>API: GET /battles/{id}/stream (SSE subscription)
    API-->>Player: Stream existing journal events (Replay Phase)

    loop Fighter Action Loop (Rounds 1..N)
        SB->>SB: Agent selects tool / action
        SB->>API: POST /internal/model (X-Sandbox-Token, prompt, tools)
        API->>API: Verify battle token & check 120 calls/min rate limit
        API->>API: Decrypt provider key via Fernet
        API->>LLM: Forward chat completion request
        LLM-->>API: Stream LLM token response
        API->>API: Redact credentials, sanitize outputs
        API-->>SB: Return model response payload
        SB->>API: POST /internal/round (artifacts, token counts, action log)
        API->>Neon: Insert into rounds & battle_events
        API-->>Player: Emit live SSE 'round_completed' event
    end

    opt Target Verification (Target-based Battle)
        SB->>Verifier: Run verify_target_submission()
        Verifier->>Verifier: Apply _command_guard & strip host secrets
        Verifier->>Verifier: Execute visible & hidden test commands
        Verifier-->>SB: Return TargetVerificationResult
    end

    SB->>API: POST /internal/finalize (artifacts, outcomes, verification marker)
    API->>API: Evaluate deterministic scoring rules & passing tests
    
    opt Subjective Rubric Evaluation
        API->>Judge: Request evaluation with rubric and fighter artifacts
        Judge-->>API: Return score breakdown and justification
    end

    API->>Neon: Insert score records into scores table
    API->>Neon: Update Battle (status: 'completed', winner, duration)
    API->>Neon: Recalculate Elo ratings in leaderboard table
    API->>Neon: Store winning skills into pgvector memories
    API-->>Player: Emit live SSE 'battle_completed' event & close stream
```

---

### 3.3 Neon Postgres & Vector Database Schema

```mermaid
erDiagram
    FORMATS ||--o{ BATTLES : "configured_by"
    FORMATS ||--o{ LEADERBOARD_ENTRIES : "categorizes"
    BATTLES ||--o{ BATTLE_PARTICIPANTS : "slots"
    BATTLES ||--o{ BATTLE_RESULTS : "authoritative_outcomes"
    BATTLES ||--o{ ROUNDS : "contains"
    BATTLES ||--o{ SCORES : "evaluated_in"
    BATTLES ||--o{ BATTLE_EVENTS : "emits"
    BATTLES ||--o{ MEMORIES : "generates"
    PROVIDERS ||--o{ BATTLES : "supplies_models"

    FORMATS {
        string id PK "uuid hex"
        string name "Format name (e.g. build-break)"
        string engine "Engine identifier"
        jsonb config "Roles, phases, rubrics"
        timestamptz created_at
        timestamptz updated_at
    }

    PROVIDERS {
        string id PK "uuid hex"
        string user_id "Appwrite user ID"
        string name "Provider display name"
        text base_url "Endpoint URL"
        text encrypted_key "Fernet ciphertext"
        string masked_key "Key preview (e.g. sk-...1234)"
        string auth_style "Bearer / Header auth"
        string model_name "Target model identifier"
        timestamptz created_at
        timestamptz updated_at
    }

    BATTLES {
        string id PK "uuid hex"
        string user_id "Appwrite user ID"
        string format_id FK "Format reference"
        string target_id "Target library ID (nullable)"
        string status "queued | running | completed | failed | cancelled"
        int arena_size "Fighter slot count"
        int timeout_seconds "Execution timeout"
        string round_visibility "isolated | open"
        string target_manifest_hash "Immutable manifest hash"
        string draft_id "Originating battle draft ID"
        boolean ranked "Ranked / casual match flag"
        jsonb battle_config "Resolved runtime config"
        boolean saved "User bookmark flag"
        timestamptz finalized_at "Authoritative finalization timestamp"
        timestamptz created_at
        timestamptz updated_at
    }

    BATTLE_PARTICIPANTS {
        string id PK "uuid hex"
        string battle_id FK "Battle reference"
        string model_id "Fighter model identifier"
        int position "Slot index (0..N)"
        string role "Fighter role (builder, breaker, etc.)"
    }

    BATTLE_RESULTS {
        string id PK "uuid hex"
        string battle_id FK "Battle reference"
        string phase "Phase name"
        string role "Fighter role"
        string model_id "Model identifier"
        string outcome "Canonical outcome (TEST_PASS, etc.)"
        boolean passed "Pass / fail flag"
        int steps "Tool steps count"
        jsonb metadata "Evidence metadata"
        timestamptz created_at
    }

    ROUNDS {
        string id PK "uuid hex"
        string battle_id FK "Battle reference"
        int round_index "Zero-based round index"
        string model_id "Acting model ID"
        text content "Redacted message content"
        jsonb artifacts "Generated artifacts / code"
        int token_count "Total round tokens"
        int duration_ms "Round elapsed milliseconds"
        timestamptz created_at
    }

    SCORES {
        string id PK "uuid hex"
        string battle_id FK "Battle reference"
        string model_id "Scored model ID"
        float score "Normalized score (0.0 - 1.0)"
        jsonb breakdown "Metric level scores"
        string judge_model "Model or 'deterministic'"
        text justification "Scoring reasoning"
        timestamptz created_at
    }

    BATTLE_EVENTS {
        string id PK "uuid hex"
        string battle_id FK "Battle reference"
        int sequence "Monotonic sequence number"
        string event_type "event name (e.g. round_completed)"
        jsonb payload "Event payload data"
        timestamptz timestamp
    }

    LEADERBOARD_ENTRIES {
        string id PK "uuid hex"
        string model_id "Model identifier"
        string format_id FK "Format identifier"
        float elo "Current Elo rating (default 1200)"
        int matches_played "Total battles"
        int wins "Total victories"
        int losses "Total defeats"
        int draws "Total draws"
        timestamptz updated_at
    }

    MEMORIES {
        string id PK "uuid hex"
        string user_id "Appwrite user ID"
        string battle_id FK "Battle reference"
        string category "fewshot | skill_strategy"
        text summary "Natural language summary"
        jsonb details "Skill execution telemetry"
        vector_1536 embedding "pgvector cosine embedding"
        timestamptz created_at
    }

    SKILL_RECORDS {
        string id PK "uuid hex"
        string name "Canonical skill identifier"
        string category "coding | security | testing"
        string version "Semantic version"
        text description "Skill capability summary"
        jsonb runtime_env "Required packages / tools"
        timestamptz created_at
    }
```

---

### 3.4 Battle Execution State Machine

```mermaid
stateDiagram-v2
    [*] --> Draft : User starts architect session (/battle-drafts)
    Draft --> Draft : Patch spec / post messages
    Draft --> Queued : POST /battles or /launch
    
    [*] --> Queued : Direct POST /battles
    
    Queued --> Running : sandbox_launcher boots Modal MicroVM
    Queued --> Failed : SandboxBootError or pre-flight check failure
    Queued --> Cancelled : User triggers POST /battles/{id}/cancel (row locked)
    
    Running --> Completed : finalization commits with trusted evidence (row locked)
    Running --> Failed : Unhandled runner error, reaper timeout, or fail_closed
    Running --> Cancelled : User triggers POST /battles/{id}/cancel (row locked)
    
    Completed --> [*]
    Failed --> [*]
    Cancelled --> [*]
```

> **In-Flight Evaluation & Terminal Concurrency Invariants**:
> - **Database Status Constraint**: PostgreSQL table `battles` enforces `CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'cancelled')", name="ck_battles_status")`.
> - **In-Flight Evaluation**: While evidence is processed by `finalization.py`, the row remains in `running` status under an active row-level lock (`SELECT ... FOR UPDATE`). It commits atomically to `completed` or `failed`.
> - **Cancel Authority**: `POST /battles/{id}/cancel` acquires `with_for_update()`. If the battle is already in a terminal status (`completed`, `failed`) or has `finalized_at` set, cancellation is rejected with `HTTP 409 Conflict`. If already `cancelled`, it returns idempotently without side-effects.

---

## 4. Functional Clusters & Component Taxonomy

The codebase is organized into six functional clusters:

### Cluster 1: Player Plane & Real-Time Client (`frontend/src/`)
- [`frontend/src/App.tsx`](file:///Users/villain/Developer/seekharness/agent-arena/frontend/src/App.tsx): Route-level code splitting via `React.lazy` and `Suspense`, mounting pages for Battles, Targets, Providers, Leaderboard, and Architect.
- [`frontend/src/lib/api.ts`](file:///Users/villain/Developer/seekharness/agent-arena/frontend/src/lib/api.ts): API client providing strongly typed HTTP methods and `streamBattle()`, featuring exponential jittered backoff (up to 8 retry attempts) and client-side event deduplication using durable event IDs.
- [`frontend/src/pages/BattleView.tsx`](file:///Users/villain/Developer/seekharness/agent-arena/frontend/src/pages/BattleView.tsx): Dual-agent split-pane console, rendering tool calls, streaming token output, test outputs, and judge justifications.

### Cluster 2: Trusted Control Plane & Route Registry (`backend/agent_arena/`)
- [`backend/agent_arena/main.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/main.py): FastAPI application initialization, CORS middleware, lifespan event handlers, and router mounting.
- [`backend/agent_arena/auth.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/auth.py): User identity validation via Appwrite Cloud Account SDK (`get_current_user`), resource ownership checks (`require_owner`).
- [`backend/agent_arena/battles.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/battles.py): Battle creation (`create_battle`), active concurrency limiter (max 5 per user), cancellation with active row locks, bookmark saving (`POST /battles/{id}/save` without mock score generation), and journal streaming (`GET /battles/{id}/stream`).
- [`backend/agent_arena/internal_router.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/internal_router.py): Hidden endpoint registry for sandboxes (`/internal/model`, `/internal/round`, `/internal/finalize`, `/internal/reap`), authenticated via `X-Sandbox-Token` with a 120 calls/min rate limiter.
- [`backend/agent_arena/providers.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/providers.py): Model provider resolution, host catalog management, and Fernet encryption/decryption of BYOK credentials.

### Cluster 3: Sandbox Runtime & Isolation Engine (`backend/agent_arena/sandbox/`)
- [`backend/agent_arena/sandbox_launcher.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/sandbox_launcher.py): Spawns Modal Sandboxes with ephemeral `BATTLE_TOKEN`, frozen bootstrap JSON, mounted target libraries, and skills root.
- [`backend/agent_arena/sandbox/runner.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/sandbox/runner.py): Execution loop executing turns, managing fighter state machines, capturing standard output, and coordinating round transitions.
- [`backend/agent_arena/sandbox/client.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/sandbox/client.py): Python HTTP client within the sandbox making authenticated requests back to the control plane.
- [`backend/agent_arena/sandbox/executors/_command_guard.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/sandbox/executors/_command_guard.py): Deterministic bash command sanitizer rejecting path traversal, absolute paths, network egress, and dangerous binaries.
- [`backend/agent_arena/ssrf.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/ssrf.py): IP and domain verification blocking private IP blocks, cloud metadata endpoints (169.254.169.254), and loopback interfaces.

### Cluster 4: Persistence & Vector Layer (`backend/agent_arena/persistence/`)
- [`backend/agent_arena/persistence/models.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/persistence/models.py): SQLAlchemy 2.x declarative models with PostgreSQL `JSONB`, `TIMESTAMPTZ`, and `pgvector` Vector(1536) columns.
- [`backend/agent_arena/persistence/service.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/persistence/service.py): Unified database operations layer implementing clean transactions via `session_scope()`.
- [`backend/agent_arena/mem0_pgvector.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/mem0_pgvector.py): Few-shot memory store indexing winning strategies and fighter tool sequences with cosine distance similarity search.

### Cluster 5: Target Library v1 & Verification Harness (`targets/` & `agent_arena/target_*.py`)
- [`targets/library/`](file:///Users/villain/Developer/seekharness/agent-arena/targets/library/): Manifest-driven challenge targets organized by categories (`coding`, `security`, `reverse-engineering`), containing starter code and test suites.
- [`backend/agent_arena/target_library.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/target_library.py): Manifest parser and schema validator checking test commands, resource limits, and partition definitions.
- [`backend/agent_arena/target_verifier.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/target_verifier.py): Hardened test runner applying environment sanitization, command guards, path restrictions, and test isolation.

### Cluster 6: Evidence Processing, Scoring & Elo Engine (`backend/agent_arena/`)
- [`backend/agent_arena/finalization.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/finalization.py): Authoritative finalization engine enforcing active row locks (`SELECT ... FOR UPDATE`), idempotency guards, trusted evidence verification, and fail-closed handling.
- [`backend/agent_arena/evidence.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/evidence.py): Compiles immutable evidence bundles from sandbox round logs and verification results.
- [`backend/agent_arena/scoring.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/scoring.py): Deterministic evaluation rules and criteria check.
- [`backend/agent_arena/judge.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/judge.py): LLM Judge invocation fallback (default: Kimi-K3) with structured scoring prompts and justifications.
- [`backend/agent_arena/elo.py`](file:///Users/villain/Developer/seekharness/agent-arena/backend/agent_arena/elo.py): Multi-player Elo calculation updating model ratings post-battle.

---

## 5. Top 5 Key Execution Flows

### 5.1 Trace 1: Battle Creation & Scoped Sandbox Launch

1. **User Request**: The React SPA issues `POST /battles` with `BattleCreate` schema and an Appwrite user JWT.
2. **Authentication & Validation**:
   - `auth.get_current_user` validates the JWT against Appwrite Cloud.
   - `battles.active_battle_count` ensures the user has fewer than 5 currently running battles.
   - `battles._validate_model_ids` verifies ownership of any BYOK model IDs or verifies host availability via `providers.is_host_model`.
   - `fighter_isolation.assert_isolated_fighter_execution` verifies sandbox isolation requirements.
3. **Database Insertion**:
   - `persistence.service.battle_create` writes a new `Battle` record to Neon with status `queued` and initializes `battle_events`.
4. **Token & Environment Generation**:
   - `sandbox_launcher.py::start_battle` is dispatched as a background task.
   - `sandbox_launcher._issue_sandbox_token(battle_id)` derives a cryptographically signed HMAC token containing `battle_id` and timestamp, verified via `internal_router._require_battle_token`.
5. **Modal Sandbox Instantiation**:
   - `sandbox_launcher._spawn_modal_sandbox` constructs the Modal Image with dependencies, mounts `/opt/arena-skills` and `/opt/arena-targets`, injects `BATTLE_TOKEN`, and launches the microVM running `backend/agent_arena/sandbox/runner.py`.
   - The battle status is updated to `running` in Neon.

### 5.2 Trace 2: Fighter Loop & `/internal/*` Proxy with Key Decryption

1. **Fighter Execution**:
   - The sandboxed runner invokes the fighter agent loop. The agent selects a tool or generates an LLM prompt.
2. **Sandbox Callback**:
   - The sandbox HTTP client calls `POST /internal/model` on the FastAPI backend passing header `X-Sandbox-Token: <token>`.
3. **Backend Authorization & Rate Limiting**:
   - `internal_router._require_battle_token` validates the token against `battle_id`.
   - `internal_router._rate_limit` checks the durable per-battle sliding window counter against the 120 calls/min threshold.
4. **Key Decryption & Provider Resolution**:
   - `providers.get_model_call_spec` retrieves the model record.
   - For BYOK models, the encrypted API key is decrypted using `crypto.decrypt_key(doc["encrypted_key"])` via Fernet.
   - For host models, the server-side host environment variable (e.g. `HOST_OPENROUTER_KEY`) is retrieved.
5. **Model Invocation & Sanitization**:
   - `llm_client.chat_completion_stream` communicates directly with the LLM API provider.
   - Model response chunks are intercepted, inspected, and redacted via `redact.sanitize_artifact` to strip sensitive signatures.
   - Sanitized responses are streamed back to the sandbox over the internal connection.
6. **Round Recording**:
   - Upon round completion, the sandbox calls `POST /internal/round` with artifacts and token counts.
   - `persistence.service.round_record` inserts the round into the `rounds` table and publishes a `round_completed` event to `event_bus`.

### 5.3 Trace 3: Target Library Verification & Security Seatbelts

1. **Verification Trigger**:
   - During battle finalization or at phase end, `target_verifier.verify_target_submission` is invoked with the fighter's workspace submission.
2. **Path Sanitization**:
   - `_blocked_submission_path` scans every submitted path, rejecting absolute paths, `..` traversals, and reserved configuration filenames matching `_HARNESS_BASENAMES` (e.g., `conftest.py`, `pytest.ini`, `setup.py`).
3. **Command Guard & SSRF Verification**:
   - Test execution commands are passed through `sandbox/executors/_command_guard.py::command_block_reason`.
   - The guard ensures no unquoted command substitutions, no parent directory references, and no usage of `curl` or `wget` unless explicitly declared via `network: true` in the target manifest.
   - Any URLs declared in the test command are checked against `ssrf.py` to block access to internal VPC subnets and metadata IP addresses.
4. **Environment Stripping**:
   - All environment variables matching regex `_STRIP_KEY_PATTERNS` (`KEY`, `SECRET`, `TOKEN`, `PASSWORD`, `APPWRITE`, `MODAL`, `DATABASE`, `URL`) are stripped.
   - Only minimal host variables in `_ALLOWED_ENV_VARS` (`PATH`, `HOME`, `TMPDIR`, `TERM`, `LANG`) are retained.
5. **Sandboxed Execution & Result Generation**:
   - The verifier executes test commands in an isolated temporary directory, capturing exit codes, standard output, and standard error, returning a typed `TargetVerificationResult` containing the immutable `TRUSTED_VERIFICATION_MARKER`.

### 5.4 Trace 4: Durable Event Journaling & Resilient SSE Streaming

1. **Event Emission**:
   - Domain actions invoke `event_bus.publish(battle_id, event_type, payload)`.
2. **Durable Persistence**:
   - `persistence.service.event_record` assigns an incremental sequence number and writes the event to the `battle_events` table in Neon Postgres.
3. **SSE Connection Initialization**:
   - The frontend calls `GET /battles/{id}/stream` with an Appwrite Bearer JWT.
   - `battles.stream_battle` verifies ownership and begins streaming using `sse_starlette.EventSourceResponse`.
4. **Journal Replay**:
   - The server queries `persistence.service.events_load(battle_id)` and immediately streams all historical events to reconstruct the full state.
5. **Live Queue Subscription**:
   - An asynchronous memory queue receives new events from `event_bus` and yields them as active SSE frames.
6. **Resilient Client Consumption**:
   - `frontend/src/lib/api.ts::streamBattle` parses events.
   - If the network drops, exponential jittered backoff reconnects up to 8 times.
   - The client tracks seen `event_id` strings and deduplicates any replayed events to avoid duplicate UI updates.

### 5.5 Trace 5: Battle Finalization, Deterministic Scoring, LLM Judge & Elo/mem0 Updates

1. **Finalization Request**:
   - The sandbox finishes and posts final artifacts to `POST /internal/finalize`.
2. **Deterministic Scoring**:
   - `scoring.py` evaluates objective verification results, checking pass/fail counts against format criteria.
   - If the criteria produce an unambiguous outcome, deterministic scores are generated.
3. **Subjective LLM Judge Evaluation**:
   - If the format requires subjective grading (or for qualitative tie-breaking), `judge.evaluate_with_judge` is called.
   - The host judge model (default: Kimi-K3 via OpenRouter) receives the rubric, task objectives, and fighter artifacts.
   - The judge returns structured scores, category breakdowns, and written justifications.
4. **Persistence of Outcomes**:
   - `persistence.service.score_record` commits final scores to the `scores` table.
   - `persistence.service.battle_result_upsert` (and `repositories.results.result_upsert`) persists authoritative per-model pass/fail verdicts, verification statuses, and metrics to `battle_results`.
   - The battle status is transitioned to `completed` in the `battles` table.
5. **Leaderboard & Memory Indexing**:
   - `elo.update_elo_ratings` recalculates ratings for all participating models based on match outcomes and updates `leaderboard_entries`.
   - `mem0_pgvector.store_winning_skills` extracts winning tool call chains and indexes the semantic summary with vector embeddings into the `memories` table.
6. **Completion Broadcast**:
   - `event_bus.publish` emits a `battle_completed` event, notifying connected frontend clients.

---

## 6. Cross-Service Data Contracts & Security Boundaries

### 6.1 Authentication Header Contracts

| Endpoint Pattern | Required Header | Validator Function | Failure Code |
|---|---|---|---|
| `POST /battles`, `GET /battles/*` | `Authorization: Bearer <appwrite_jwt>` | `auth.get_current_user` | HTTP 401 / 403 |
| `POST /internal/model` | `X-Sandbox-Token: <battle_token>` | `internal_router._require_battle_token` | HTTP 401 |
| `POST /internal/round` | `X-Sandbox-Token: <battle_token>` | `internal_router._require_battle_token` | HTTP 401 |
| `POST /internal/finalize` | `X-Sandbox-Token: <battle_token>` | `internal_router._require_battle_token` | HTTP 401 |
| `POST /internal/reap` | `X-Internal-Key: <internal_key>` | `internal_router.require_internal_key` | HTTP 401 |

### 6.2 Key Runtime Environment Variables

| Variable Name | Component | Purpose |
|---|---|---|
| `PERSISTENCE_BACKEND` | Control Plane | Defaults to `postgres` (Neon is the primary system of record for battles, events, scores, and Elo). Legacy Appwrite document persistence branches remain in `persistence/service.py` for rollback and test compatibility. |
| `APPWRITE_DUAL_WRITE` | Control Plane | Controls dual-writing to Appwrite databases during migrations (exposed in `/health`). |
| `APPWRITE_READ_FALLBACK` | Control Plane | Enables reading from Appwrite when a document is absent in PostgreSQL (exposed in `/health`). |
| `DATABASE_URL` | Control Plane | Pooled connection string to Neon PostgreSQL. |
| `DATABASE_URL_UNPOOLED` | Control Plane / Alembic | Direct connection string for DDL migrations. |
| `FERNET_KEY` | Control Plane | Symmetric encryption key used for BYOK credentials. |
| `APPWRITE_ENDPOINT` | Control Plane & SPA | Appwrite Cloud REST endpoint for JWT identity verification. |
| `APPWRITE_PROJECT_ID` | Control Plane & SPA | Appwrite Project identifier for JWT validation. |
| `BATTLE_TOKEN` | Sandbox MicroVM | Ephemeral HMAC token scoped to a single battle ID. |
| `ARENA_VERIFIER_ALLOW_INPROCESS` | Control Plane & Tests | Set to `1` in unit test suites; forbidden in production. |

---

## 7. Agent Runtime, Cognition & Tooling Engine

The SeekHarness agent execution runtime provides an open, provider-agnostic cognitive layer that bridges disparate LLM reasoning architectures into uniform execution actions within the isolated Linux microVM.

### 7.1 Multi-Dialect Tool Parsing & Normalization Engine

Different foundational models output tool invocations in wildly divergent formats. Rather than locking fighters into OpenAI-specific function calling, `backend/agent_arena/tool_protocol.py` implements a multi-dialect normalizer supporting six distinct interaction grammars:

| Dialect Name | Output Pattern | Target Models |
|---|---|---|
| `openai_native` | Native `tool_calls` JSON array with `function: {name, arguments}` | GPT-4o, Claude 3.5 Sonnet (OpenAI proxy mode), DeepSeek-V3 |
| `anthropic_native` | Native content blocks of type `tool_use` with `input` objects | Claude 3.5 Sonnet, Claude 3 Opus |
| `kimi_token_xml` | `<\|action_start\|><\|plugin\|>...<\|action_end\|>` | Moonshot Kimi / Kimi-K3 series |
| `xml_tag` | `<tool_call><name>...</name><arguments>...</arguments></tool_call>` | DeepSeek-R1, Qwen 2.5 Coder, Hermes |
| `arena_json` | Markdown fenced or bare JSON objects `{ "name": "...", "arguments": {...} }` | Open-source instruction tuned LLMs |
| `arena_legacy` | Line grammar: `TOOL <name> key=val\nEND_TOOL` | Minimal parameter models & text-only fallbacks |

#### Auto-Repair Engine
Models running multi-step reasoning often introduce syntax defects when generating JSON parameters under token pressure. The normalizer runs automated heuristic repairs before flagging a parse error:
- Unbalanced quotes, brackets, and braces are completed.
- Trailing commas in objects and arrays are stripped.
- Single-quoted string keys and values are rewritten to compliant double quotes.
- HTML entity escapes (`&quot;`, `&amp;`) are restored.

### 7.2 Tool Parsing, Auto-Repair & Execution Pipeline

```mermaid
flowchart TD
    subgraph ModelOutput["Model Response Stream"]
        RawResp["Raw LLM Completion"]
        DialectDetect{"Dialect Detector\n(tool_protocol.py)"}
    end

    subgraph Dialects["Supported Tool Dialects"]
        D1["openai_native\n(tool_calls array)"]
        D2["anthropic_native\n(tool_use blocks)"]
        D3["kimi_token_xml\n(<|action_start|>)"]
        D4["xml_tag\n(<tool_call>)"]
        D5["arena_json\n(fenced/bare JSON)"]
        D6["arena_legacy\n(TOOL line grammar)"]
    end

    subgraph Normalization["Tool Call Normalization & Repair"]
        Parser["Dialect Specific Extractor"]
        Repair{"Malformed JSON?"}
        AutoFix["Repair Engine\n(balance quotes, braces, trailing commas)"]
        Canonical["CanonicalToolCall\n(name, arguments, call_id, dialect)"]
    end

    subgraph MicroVMExec["MicroVM Execution Loop (runner.py)"]
        EmitRunning["emit_action(state='running')"]
        ToolRegistry{"Tool Name Match"}
        T_Files["Filesystem Tools\n(read, write, ls, grep, cp, mv, rm)"]
        T_Process["Process Tools\n(shell, run, install, test)"]
        T_Skills["Skill Tools\n(skills, use_skill)"]
        T_Bg["Background Jobs\n(bg, ps, kill, logs)"]
        T_Net["Network Tools\n(fetch)"]
        Sanitizer["Sanitize Output & Cap (10KB)"]
        EmitDone["emit_action(state='done'/'failed')"]
    end

    RawResp --> DialectDetect
    DialectDetect --> D1 & D2 & D3 & D4 & D5 & D6
    D1 & D2 & D3 & D4 & D5 & D6 --> Parser
    Parser --> Repair
    Repair -->|"Yes"| AutoFix
    Repair -->|"No"| Canonical
    AutoFix --> Canonical
    Canonical --> EmitRunning
    EmitRunning --> ToolRegistry
    ToolRegistry --> T_Files & T_Process & T_Skills & T_Bg & T_Net
    T_Files & T_Process & T_Skills & T_Bg & T_Net --> Sanitizer
    Sanitizer --> EmitDone
```

### 7.3 Workspace Tools & Capabilities

Fighters interact with the environment via `TOOL_SCHEMAS` defined in `tool_protocol.py`:

- **Filesystem Tools**: `read` (file viewing), `write` (file creation/overwrite), `ls` (directory listing), `grep` (regex code search), `tree` (workspace hierarchy), `cp` (copy), `mv` (move), `rm` (delete). All file operations are pinned to the fighter workdir.
- **Process & Build Tools**: `shell` (arbitrary bash command within timeout), `run` (execute executable scripts), `install` (sandbox-isolated `pip install`), `test` (invoke format-configured test command).
- **Process Orchestration**: `bg` (launch detached background process, e.g. web servers), `ps` (list running processes), `logs` (read stdout/stderr of background daemon), `kill` (terminate background job).
- **Advisory Skill Invocation**: `skills` (search and discover available skill documentation), `use_skill` (read full markdown body of specific skill).
- **Egress Tools**: `fetch` (HTTP GET fetching of documentation or external assets, subject to format network policy).

---

## 8. Knowledge Architecture, Progressive Skills & Vector Memory

The cognitive architecture separates **advisory knowledge** from **execution authority**. Skills advise the model on how to solve problems; they do not expand system permissions.

### 8.1 Progressive Skill Disclosure Pattern

Skills are structured according to the open Agent Skills specification and stored in `/opt/arena-skills/`. To prevent overwhelming context windows, loading follows a four-tier progressive disclosure model:
1. **Catalog Index**: `skills()` lists high-level categories (e.g. `debugging`, `security`, `frontend`).
2. **Semantic Search**: `skills(search="session replay token")` finds candidate skills matching keywords.
3. **Metadata Inspection**: `skills(skill="auth-flow-debugger")` returns frontmatter, license, and summary without instructions.
4. **On-Demand Body Fetch**: `use_skill("auth-flow-debugger")` loads the full markdown instructions only when the agent decides it is needed.

### 8.2 Progressive Skill Discovery & mem0 Vector Memory Pipeline

```mermaid
flowchart LR
    subgraph AgentWorkspace["Fighter Workspace Context"]
        Prompt["Fighter System Prompt\n(fighter_context.py)"]
        ToolCall["TOOL skills / use_skill"]
    end

    subgraph SkillDiscovery["Progressive Skill Discovery Loop"]
        IndexQuery["1. skills()\nBrowse categories"]
        SearchQuery["2. skills(search='...')\nKeyword search"]
        MetaInspect["3. skills(skill='...')\nRead metadata & tags"]
        BodyFetch["4. use_skill(name='...')\nFetch full body only on demand"]
    end

    subgraph SkillsStorage["Skills Subsystem & Registry"]
        DiskMount["/opt/arena-skills/\n(Canonical SKILL.md)"]
        SkillElo["Skill Registry & Elo Decay\n(skills_registry.py)\n- Initial: 1200\n- Decay: 2% per day unused\n- Difficulty offsets"]
    end

    subgraph EpisodicMemory["Episodic Memory & Learning Engine"]
        Mem0["mem0_pgvector.py\nVector(1536) Embeddings"]
        WinningCombos["Index Winning Skill Combos\n& Tool Call Patterns"]
        FutureRetrieval["Cosine Similarity Retrieval\nfor Next-Gen Battles"]
    end

    Prompt --> ToolCall
    ToolCall --> IndexQuery
    IndexQuery --> SearchQuery
    SearchQuery --> MetaInspect
    MetaInspect --> BodyFetch
    BodyFetch --> DiskMount
    DiskMount --> SkillElo
    SkillElo --> WinningCombos
    WinningCombos --> Mem0
    Mem0 --> FutureRetrieval
```

### 8.3 Skill Elo & Time-Based Decay Engine (`skills_registry.py`)

Skills themselves participate in an Elo rating system based on match outcomes:
- **Base Rating**: Every newly indexed skill starts with `INITIAL_RATING = 1200`.
- **Difficulty Offsets**: Target difficulty modifies expected outcomes: `advanced: -100`, `expert: -200`. A skill used in an expert challenge gains more rating points upon victory.
- **Time Decay**: Unused skills undergo automatic decay toward the baseline:
  $$\text{decay\_factor} = \max(0.0, 1.0 - 0.02 \times \text{days\_unused})$$
  This ensures stale skills that dominated older formats do not permanently squat on top leaderboard ranks.

### 8.4 Episodic Memory & Vector Embeddings (`mem0_pgvector.py`)

Post-battle telemetry is transformed into structured semantic memories. Winning sequences (tool combinations, effective search patterns, test strategies) are vectorized using 1536-dimensional embeddings and stored in Neon Postgres `memories` table with `pgvector 0.5.0` cosine indexing, allowing future agents to retrieve few-shot winning exemplars for similar targets.

---

## 9. Battle Arenas, Formats & Target Library v1

### 9.1 Six Battle Format Engines (`seed_formats.py`)

Agent Arena hosts 25+ curated formats built across six primary execution engines:

| Engine Identifier | Interaction Paradigm | Typical Formats | Win Condition Mechanism |
|---|---|---|---|
| `build_and_break` | Asymmetric multi-phase duel (Builder creates defense; Breaker attacks) | Web Security Duel, API Fortress, Auth Gate | Secret extraction, file marker presence, or exploit proof vs passing defensive tests |
| `same_target_race` | Parallel symmetric speed & quality coding competition | Code Golf, Bug Squashing, Optimization Race | First to pass hidden verification harness with fewest tool steps |
| `script_vs_defense` | Adversarial automation vs system hardening | Rate Limit Bypass, SQL Injection Defense | Test harness verifies whether exploit script pierces hardened policy |
| `direct_duel` | Head-to-head turn-based challenge | Code Refactoring, Algorithm Race | Relative judge rubric scoring and deterministic correctness comparisons |
| `agent_vs_agent` | Multi-agent collaboration or competitive negotiation | Protocol Negotiation, Peer Review Duel | Mutual consensus marker or judge assessment of deliverables |
| `high_complexity` | Unconstrained full toolbelt multi-phase sandbox (Omni build/break) | Omni Escape, Level-4 Full Toolbelt | Adversarial win predicates (`SECRET_LEAKED`, `WIN_FILE_CREATED`) |

---

### 9.2 Target Library v1 Architecture & Handoff Pipeline

Target packages reside under `targets/library/<target_id>/` and follow a strict, versioned four-partition schema:

```
targets/library/<target_id>/
├── target.yaml          # Canonical contract, runtime limits, and verification commands
├── README.md            # Public mission brief presented to fighters
├── starter/             # Base source code materialized into fighter workspace
├── tests/visible/       # Feedback test suite exposed to the fighter for iteration
└── tests/hidden/        # Private evaluator test suite (mounted only during verification)
```

```mermaid
flowchart LR
    subgraph TargetPackage["Target Library Package (targets/library/<id>/)"]
        Manifest["target.yaml (Manifest)"]
        StarterTree["starter/ (Base repository)"]
        VisibleTests["tests/visible/ (Public feedback harness)"]
        HiddenTests["tests/hidden/ (Evaluator only)"]
        RefGold["reference/ (Gold solution)"]
    end

    subgraph Phase1["Phase 1: Builder / Solo Fighter"]
        BuilderWork["work_builder/ workspace"]
        StarterTree -->|"mount"| BuilderWork
        VisibleTests -->|"mount"| BuilderWork
        BuilderWork -->|"write deliverables"| BuilderArtifacts["Builder Artifacts"]
    end

    subgraph HandoffGate["Builder-to-Breaker Handoff Gate (battle_plan.py)"]
        Allowlist{"Path in workspace.handoff_allowlist?"}
        Snapshot["In-Memory Bytes Snapshot & SHA-256 Manifest"]
        Purge["Destroy Builder Workspace Disk"]
        BuilderArtifacts --> Allowlist
        Allowlist -->|"Approved"| Snapshot
        Allowlist -->|"Forbidden/Traversal"| Reject["Reject & Log"]
        Snapshot --> Purge
    end

    subgraph Phase2["Phase 2: Breaker Fighter"]
        BreakerWork["work_breaker/ fresh workspace"]
        Purge -.-> BreakerWork
        Snapshot -->|"Materialize allowlisted bytes"| BreakerWork
    end

    subgraph VerifierGate["Trusted Target Verifier (target_verifier.py)"]
        CleanWorkspace["Isolated Temp Workspace"]
        BreakerWork -->|"submitted code"| CleanWorkspace
        HiddenTests -->|"mount evaluator tests"| CleanWorkspace
        RefGold -. "never exposed" .-> CleanWorkspace
        Seatbelts["_command_guard + SSRF guard + _ALLOWED_ENV_VARS"]
        CleanWorkspace --> Seatbelts
        Seatbelts --> PassFail["Deterministic Verification Result"]
    end
```

### 9.3 Benchmark Target Catalog Summary

The Target Library v1 includes 17 canonical coding and cybersecurity targets spanning difficulty tiers:

| Target ID | Category | Difficulty | Runtime | Core Challenge Focus |
|---|---|---|---|---|
| `broken-package-recovery` | Debugging | Novice | `node22` | Repair syntax errors and corrupted dependencies in `package.json` |
| `authentication-gate` | Security | Novice | `python312` | Audit broken password hashing and enforce secure auth gate |
| `sql-login-service` | Security | General | `python312` | Fix SQL injection vulnerability in legacy authentication API |
| `session-replay-defense` | Web Security | Advanced | `node22` | Mitigate replay attacks by implementing cryptographically signed nonces |
| `fullstack-bank-vault` | Fullstack | Advanced | `python312` | Asymmetric financial ledger vulnerability repair under concurrency |
| `fullstack-ssrf-portal` | Security | Expert | `python312` | Mitigate server-side request forgery while maintaining webhook functionality |
| `graphql-data-leakage` | API Security | Expert | `node22` | Prevent introspection abuse and unauthorized field-level data extraction |
| `migration-disaster` | Database | Advanced | `python312` | Reconcile divergent Alembic database migrations without data loss |
| `makefile-from-hell` | Systems | Expert | `c_cpp` | Resolve circular dependency deadlock and race conditions in GNU Makefile |
| `tinyshop` | Fullstack | General | `node22` | Repair broken checkout race condition and inventory decrement bugs |

---

## 10. Omni-Executor & Next-Gen Toolbelt Engine

The **Omni-Executor** (`backend/agent_arena/sandbox/executors/formats/omni_code_sandbox.py`) represents the pinnacle of agent autonomy within SeekHarness. Conceived to answer *"how much access can we give agents to see what they can truly accomplish under adversarial conditions"*, it grants agents four progressive capability levels simultaneously:

### 10.1 Four Levels of Agent Tool Access

```
+---------------------------------------------------------------------------------------+
| LEVEL 4: CONTROLLED OPEN INTERNET                                                     |
| · HTTP/HTTPS egress via FETCH tool                                                    |
| · External documentation lookup (GitHub, Python/Node docs, CVE feeds)                |
| · Private VPC, metadata service (169.254.169.254), and loopback blocked by ssrf.py    |
+---------------------------------------------------------------------------------------+
                                           ▲
+---------------------------------------------------------------------------------------+
| LEVEL 3: ADVERSARIAL EXECUTION LOOP                                                   |
| · Multi-turn Red Team vs Blue Team dynamics (up to 6 turns, 6 tool calls per turn)   |
| · Real-time observation telemetry fed back into model context                         |
| · Explicit escape and defense win conditions                                          |
+---------------------------------------------------------------------------------------+
                                           ▲
+---------------------------------------------------------------------------------------+
| LEVEL 2: FULL TOOLBELT (KILO / ADVANCED ORCHESTRATION STYLE)                          |
| · THINK: Sequential thinking chain-of-thought logging with branching hypotheses       |
| · FETCH: Firecrawl-like web retrieval with 20KB truncation                            |
| · SEARCH: Targeted query lookup                                                       |
| · AUDIT: In-situ OWASP security scanning (detects eval, subprocess, path traversal)   |
+---------------------------------------------------------------------------------------+
                                           ▲
+---------------------------------------------------------------------------------------+
| LEVEL 1: DIRECT CODE & SYSTEM EXECUTION                                               |
| · EXEC: Arbitrary Python/Bash execution with 180s timeout                             |
| · INSTALL: Live pip package installation in microVM sandbox                           |
| · FILES: Atomic write, read, and directory navigation                                 |
+---------------------------------------------------------------------------------------+
```

### 10.2 Adversarial Escape Win Condition Predicates

In Level 3/4 Build & Break competitions, breakers attempt to bypass sandbox confines crafted by builders. The outcome is determined by unambiguous predicate checks:

1. `SECRET_LEAKED`: The breaker prints or returns the target secret `FLAG{omni-escape-top-secret-42}`.
2. `WIN_FILE_CREATED`: The breaker successfully creates the sentinel file `ESCAPE_OK` in the root workspace.
3. `WIN_MARKER_FOUND`: The breaker's standard execution output prints `ESCAPE_OK`.
4. `SECRET_IN_WORK`: The secret token appears inside files within the breaker workspace.
5. `NO_ESCAPE`: The builder's defense successfully holds through all rounds.

---

## 11. Foundational Architecture Intent & Core Invariants

The historical design intentions, foundational implementation gates, and core invariants for SeekHarness are maintained in:

👉 **[`agent-arena/docs/architecture/SEEKHARNESS_ORIGINAL_INTENT.md`](file:///Users/villain/Developer/seekharness/agent-arena/docs/architecture/SEEKHARNESS_ORIGINAL_INTENT.md)**

### Summary of Non-Negotiable Engineering Invariants

1. **Air-Gapped Credentials**: Never send an API key, database URL, Fernet master key, or global internal key to the player browser or a fighter sandbox.
2. **Deterministic Evidence Superiority**: Never use an LLM’s text output as proof that a test passed, a file exists, or a policy held.
3. **Partition Isolation**: Never expose hidden tests, reference solutions, evaluator paths, or an opponent fighter's workspace to an agent.
4. **Live Telemetry Integrity**: Never use a browser-side mock stream or synthetic score to stand in for live execution state.
5. **Anti-Hallucination Scoring**: Never score incomplete evidence as if it were a verified loss or win; record `None` or `incomplete_evidence`.
6. **Least Privilege Capabilities**: Never promote sandbox capabilities (network access, database access, host tooling) without explicit format configuration and security seatbelts.
7. **Frozen Battle Contracts**: Keep custom Battle Drafts as frozen, revisioned inputs; never permit mid-run prompt, target, or configuration mutation.

---

## 12. Master Engineering Governance & Subsystem Architecture Suite

To govern the next phases of benchmark maturation, authority isolation, and scientific evaluation, detailed modular specifications have been authored:

### 12.1 Program Execution Roadmap & Gates
👉 **[`agent-arena/docs/architecture/MASTER_ROADMAP.md`](file:///Users/villain/Developer/seekharness/agent-arena/docs/architecture/MASTER_ROADMAP.md)**
- **Governing Plan**: Master Engineering Plan v1.1.
- **Acceptance Gates C1–C5**: Freezing Change Set C, DeepSeek adversarial review, disposable local PostgreSQL concurrency testing (C1–C9), and final hermetic regression.
- **The 44-Step Master Execution Checklist**: Linear dependency sequence from code freeze through 18-battle pilot, 90-battle evaluation, and adaptive learning.
- **The 15 Non-Negotiable Directives**: Strict rules forbidding benchmark contamination, unmetered egress, and premature learning.

### 12.2 Skill Graph v0.3 Canonical Specification & 63-Skill Catalog
👉 **[`agent-arena/docs/architecture/SKILL_GRAPH_V03.md`](file:///Users/villain/Developer/seekharness/agent-arena/docs/architecture/SKILL_GRAPH_V03.md)**
- **Frozen Taxonomy**: Exactly 63 canonical skills categorized across 11 functional domains.
- **Canonical Schema v2**: 16-field specification defining advisory indexes, roles, runtimes, and discovery signals.
- **Fighter Discovery API**: Non-restrictive progressive disclosure (`skills()`, `skills(index=...)`, `skills(search=...)`, `skills(skill=...)`, `use_skill(id)`).
- **Deterministic Lexical Search Engine**: Scoring weights prioritizing problem-class evidence over generic runtime overlap.
- **Navigation Telemetry**: Deterministic `strategy_signature_v1` generation for model comparison.

### 12.3 Benchmark Secrecy, Runtime Fidelity & Controlled Web Research
👉 **[`agent-arena/docs/architecture/BENCHMARK_SECRECY_AND_RUNTIME_FIDELITY.md`](file:///Users/villain/Developer/seekharness/agent-arena/docs/architecture/BENCHMARK_SECRECY_AND_RUNTIME_FIDELITY.md)**
- **Phase S (Benchmark Secrecy)**: Separating public target repositories from private evaluator packages (`targets/evaluators/`), materialized via `materialize_fighter_visible_library` into `/opt/arena-targets` without mounting hidden tests into the fighter execution plane.
- **Phase R (Runtime Fidelity)**: Canonical runtime contracts (`python311`, `python311-fastapi`, `python311-sqlite`, `node22`, `linux-gcc-make`), dynamic sandbox container materialization, and complete elimination of palindrome fallbacks.
- **Phase D3 (Controlled Web Research)**: Three research modes (`off`, `snapshot`, `live`), host-mediated proxying, SSRF/private IP blocking, credential stripping, and step accounting.

