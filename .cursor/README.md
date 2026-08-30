# Agent Arena Cursor workspace

High-autonomy local engineering. Tool calls auto-approve. Only destructive / billing actions stay denied.

This directory is the only place this configuration task may change. Application source is out of scope here.

## Team

| Agent | Model | Mode | Use |
| --- | --- | --- | --- |
| `lead-engineer` | Grok 4.6 High (`grok-4.6[effort=high]`) | write | Architecture, finalization, concurrency, isolation, migrations |
| `implementation-worker` | Grok 4.6 High (`grok-4.6[effort=high]`) | write | Routine wiring, UI/backend glue, already-approved plans |
| `test-debugger` | Grok 4.6 High (`grok-4.6[effort=high]`) | readonly | Reproduce, trace, audit test claims |

All three project subagents are pinned to Grok 4.6 High in `.cursor/agents/*.md`. Do not default subagents to Composer, Luna, XHigh, Sol, or Opus.

DeepSeek Harness remains the external independent reviewer. It is not a Cursor subagent in this repo.

## Local autonomy (AUTO)

Cursor auto-approves tool and shell use in this workspace, including git, tests, builds, deploys, Modal, Vercel, Appwrite, browser, MCP, and project subagent delegation.

IDE Run Mode is **Run Everything** / unrestricted auto-approve.

## Denied (BLOCK)

Hooks still deny force push, `git reset --hard`, `git clean`, dangerous `rm -rf`, production `DROP`/`TRUNCATE`, billing/domain/credit purchases, cloud-project deletion, and `sudo`.

## Skills

| Skill | Purpose |
| --- | --- |
| `battle-trace-audit` | Reconstruct a battle and classify MODEL / TOOL_INTERFACE / TARGET_RUNTIME / TARGET_BUNDLE / SANDBOX / VERIFIER / FINALIZATION / PRESENTATION_ONLY |
| `finalization-audit` | Caller authority, terminal state, duplicate finalize, result identity, transactions, Elo/skill races, memory provenance, rollback |
| `target-integrity-audit` | Manifest, runtime, public/private files, evaluator exposure, Builder/Breaker, read/shell/Python/subprocess/symlink/Git leakage |
| `deployment-alignment` | Read-only HEAD vs origin/main vs dirty tree vs proven Modal/Vercel/migration state |
| `regression-gate` | Focused → subsystem → Change Set A → B → C → target security → hermetic backend → frontend if relevant |

## Commands

| Command | Mode |
| --- | --- |
| `/review-diff` | Read-only diff review (BLOCKER / MAJOR / MINOR) |
| `/safe-tests` | May run local hermetic tests automatically |
| `/precommit-gate` | Read-only commit-boundary review; does not commit |
| `/audit-target` | Read-only target-integrity workflow |
| `/deployment-status` | Read-only deployment alignment |

## Enforcement map

| Layer | File | Role |
| --- | --- | --- |
| IDE auto-approve | `.cursor/permissions.json` | `*` terminal/MCP allowlists; empty `block_instructions` |
| CLI | `.cursor/cli.json` | Separate allow/deny tokens; deny wins |
| Hard shell / MCP | `.cursor/hooks.json` | `allow` / `ask` / `deny` |
| Session end | `.cursor/hooks/session-status.sh` | Logs `git status --short` and `git diff --check` (output unused) |

`autoRun` is steering, not a security boundary. Hooks are the hard gate.

`mcpAllowlist` is auto-approval only. It does not make a tool read-only. This project does not add fake `enabled: false` MCP entries.

## Tests

Intended external integration gate: `ARENA_INTEGRATION_TESTS=1` (plus `ARENA_PG_TEST_URL` for real Postgres). Default `pytest.ini` deselects `modal`, `integration`, `postgres`, and `provider_eval`. Do not claim further application test hardening than `hermetic.py` / `conftest.py` already implement.

Default hermetic command:

```text
backend/.venv/bin/python -m pytest --ignore=tests/evals
```

## MCP (manual Customize toggles)

Do not uninstall global integrations. In this workspace, open **Customize** and toggle:

- Keep: built-in browser, `codebase-memory-mcp` (local stdio)
- Disable: Appwrite (plugin + `user-appwrite`), filesystem (`~/Documents`), Notion, Lucid, Strike, Vercel
- Neon: already absent/disconnected — leave it off
- Do not add GitHub MCP or Modal MCP

A `beforeMCPExecution` hook still denies Vercel billing/purchase tools and filesystem MCP writes outside the workspace.

## Main model (manual)

1. In Agent chat, the parent model can stay whatever you pick. Project **subagents always use Grok 4.6 High**.
2. If Explore is pinned to Grok 4.6 XHigh, open **Cursor Settings → Agents** (model / Explore override) and lower it to inherit or Grok 4.6 (not XHigh). Do not edit private state databases.

Subagent models stay pinned in `.cursor/agents/*.md`. Do not change those pins to Composer, Luna, XHigh, Sol, or Opus.
