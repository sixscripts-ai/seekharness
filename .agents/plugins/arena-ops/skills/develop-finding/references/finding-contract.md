# Finding contract

Single writer: `develop-finding`. Single validator: `backend/agent_arena/evidence.py` via `build_phase_result` / `build_battle_evidence`. Do not add a second validator.

A Finding is Evidence when a Battle later has `findings.v1.json` in EXECUTOR_RESULT `files`. It is never an Official Result. Severity never sets `passed`, score, or winner.

## Artifact

- Filename: `findings.v1.json`
- Default off-battle path: `scratch/findings.v1.json` (or an explicit operator path)
- Envelope schema: `arena-finding-v1`
- Evidence schema version stays `1` (additive `findings` + `findings_ingest` on the phase)

```json
{
  "schema": "arena-finding-v1",
  "findings": [
    {
      "id": "auth-001",
      "domain": "auth",
      "severity": "high",
      "title": "Admin route skips session gate",
      "witness": "GET /admin returns 200 without a session cookie",
      "affected_files": ["src/admin.py"],
      "confidence": 0.8,
      "remediation": "Require an authenticated session before /admin."
    }
  ]
}
```

## Fields

| Field | Rule |
|---|---|
| `id` | Non-empty string |
| `domain` | `auth` \| `authz` \| `secrets` \| `http_api` \| `sandbox` \| `dependency` |
| `severity` | `critical` \| `high` \| `medium` \| `low` \| `info` |
| `title` | Non-empty string |
| `witness` | Non-empty string; redact secret-like values |
| `affected_files` | List of strings; Hidden Evaluator paths are stripped on ingest |
| `confidence` | Number in `[0, 1]` |
| `remediation` | String; redact secret-like values |

Drop keys that look like Official Result (`passed`, `score`, `winner`, `official_result`). Do not write `exploit_evidence`.

## Ingest (`findings_ingest`)

| File state | Ingest | Phase findings | Battle |
|---|---|---|---|
| Missing | `absent` | `[]` | Not incomplete |
| Valid envelope | `valid` | Projected list | Other facts unchanged |
| Invalid JSON / unknown severity / missing witness | `invalid` | `[]` | Other facts intact; no Fail-closed Outcome |

## Candidate staging (domain skills only)

Domain skills write `scratch/candidates/<domain>.json`. They must not write `findings.v1.json`.

```json
{
  "candidate_schema": "arena-finding-candidate-v1",
  "domain": "auth",
  "title": "...",
  "witness": "...",
  "affected_files": ["src/admin.py"],
  "severity_hint": "high",
  "confidence_hint": 0.8,
  "remediation": "..."
}
```

## Projection

Public-safe projection (owned by Evidence, not skills):

- Strip Hidden Evaluator paths (`tests/hidden`, `evaluators/`, `reference/`, `hidden_eval`)
- Redact secret values with the Arena `redact` adapter
- Keep only the Finding public fields
