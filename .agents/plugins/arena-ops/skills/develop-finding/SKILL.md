---
name: develop-finding
description: >
  Use this skill when operator domain candidates are ready and must be written as findings.v1.json. Sole writer of the Finding artifact. Never sets Official Result fields.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Develop Finding

## Overview
Sole writer of `findings.v1.json`. Reads `arena-finding-candidate-v1` staging files and emits the `arena-finding-v1` envelope. A Finding is a structured risk claim. When a Battle later has this file in EXECUTOR_RESULT `files`, Evidence ingest attaches it. It is never an Official Result. Severity never sets passed, score, or winner.

## Activation
Use after `discover-evidence` (or a single domain skill) has staged candidates. Off-battle default: write `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`.

## Required Inputs
- One or more candidates under `scratch/candidates/` (or an explicit operator path)
- Output path: `scratch/findings.v1.json` unless the operator names another path

## Workflow
1. **Read candidates**: Load `arena-finding-candidate-v1` objects. Ignore files that are already `findings.v1.json` from a prior run unless the operator asked to replace them.
2. **Normalize fields**: Map `severity_hint` → `severity`, `confidence_hint` → `confidence`. Assign `id` as `{domain}-{nnn}`. Drop Official Result keys (`passed`, `score`, `winner`, `official_result`).
3. **Refuse unsafe content**: Redact secret-like values. Strip Hidden Evaluator paths from `affected_files`. Do not write `exploit_evidence`.
4. **Write envelope**: `{"schema": "arena-finding-v1", "findings": [...]}` to the operator path.
5. **Optional check**: Run `scripts/normalize_findings.py` so `build_phase_result` reports `findings_ingest=valid`. That script imports `agent_arena.evidence`; do not add a second validator.

## Output Contract
One `findings.v1.json` envelope. Fields per Finding: `id`, `domain`, `severity`, `title`, `witness`, `affected_files`, `confidence`, `remediation`. Domain enum: `auth` | `authz` | `secrets` | `http_api` | `sandbox` | `dependency`. Severity enum: `critical` | `high` | `medium` | `low` | `info`.

## Available Scripts
- **`scripts/normalize_findings.py`** — preview ingest via `agent_arena.evidence.build_phase_result`. No second validator.

## References
Read `references/finding-contract.md` for the envelope, candidate shape, ingest states, and projection rules.

## Safety and Permissions
Operator-mounted only. Fighters must not receive this artifact as a skill body. Never print secrets. Never paste Hidden Evaluator contents. No exploits, exploit PoCs, or attack procedures. Do not write Official Result fields.

## Failure Handling
If a candidate is missing `witness`, has unknown severity, or is not valid JSON, omit it and tell the operator. Do not write an invalid envelope and call it valid. An invalid file later ingested by a Battle is `findings_ingest=invalid` with an empty list; that is not a Fail-closed Outcome.

## Gotchas
- Domain skills never write this file. If they did, stop and rewrite through this skill.
- Missing file on a Battle is `absent`, not incomplete Evidence.
- Distinct from `exploit_evidence`. Do not copy candidates into that object.

## Examples
**Input**: `scratch/candidates/auth.json` with a witnessed session-gate gap.

**Action**: Write `scratch/findings.v1.json` with `schema=arena-finding-v1` and one Finding. Do not set winner, score, or passed.

## Validation
Envelope schema is `arena-finding-v1`. Optional: `backend/.venv/bin/python` on `scripts/normalize_findings.py` prints `findings_ingest=valid`.

## Compatibility
Cursor, Agent Arena operator
