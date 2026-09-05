---
name: discover-secrets-evidence
description: >
  Use this skill when an operator needs credential-leakage evidence staged as a secrets candidate for develop-finding, without writing findings.v1.json, Official Result fields, or echoing secret values.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Discover Secrets Evidence

## Overview
Operator-only review of credential leakage. Emits one `arena-finding-candidate-v1` record with domain `secrets`. A Finding is a structured risk claim. When a Battle later ingests `findings.v1.json` it is Evidence. It is never an Official Result. Severity never sets passed, score, or winner. Never print secrets; use `[REDACTED]` in witness and remediation. Never echo API keys.

## Activation
Use when an operator asks for secrets evidence (committed keys, leaked tokens, plaintext credentials). Off-battle: tell the operator these are candidates for `develop-finding`, which writes `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`.

## Required Inputs
- Review scope (paths, env files, logs, transcripts)
- Output path: `scratch/candidates/secrets.json` or an explicit operator path

## Workflow
1. **Scope Leakage**: Locate credential sources and leak paths only.
2. **Collect Witness**: Cite files and leak location. Replace every secret value with `[REDACTED]`.
3. **Draft Candidate**: Fill `arena-finding-candidate-v1` with domain `secrets`.
4. **Stage File**: Write the candidate. Never write `findings.v1.json`.
5. **Hand Off**: Point the operator at `develop-finding`. Fighters must not receive this review.

## Output Contract
Write only `scratch/candidates/secrets.json` (or an explicit operator path). Shape: `candidate_schema`, `domain` (`secrets`), `title`, `witness`, `affected_files`, `severity_hint`, `confidence_hint`, `remediation`. Witness and remediation must use `[REDACTED]`. No Official Result keys. No `exploit_evidence`.

## Available Scripts
*(No scripts provided)*

## References
Read `references/REFERENCE.md` for the Finding contract pointer and secrets notes.

## Safety and Permissions
Operator-mounted only. Fighters must not receive operator reviews or Hidden Evaluator material. Never print secrets or echo API keys. Do not write exploits, exploit PoCs, or attack procedures. Do not write Official Result fields (`passed`, `score`, `winner`) or `findings.v1.json`.

## Failure Handling
If leakage cannot be shown without pasting a secret, stop and ask the operator for a redacted path. Do not invent a candidate.

## Gotchas
- Provider/API credentials remain backend-only. Do not copy them into chat or the candidate.
- Do not populate Official Result fields. Severity is a hint only.

## Examples
**Input**: Operator finds a host API key in a committed dotenv example.

**Action**: Stage `scratch/candidates/secrets.json` with witness `HOST_*_KEY=[REDACTED] in .env.example` and a remediation to remove it. Do not echo the key. Do not write `findings.v1.json`.

## Validation
Confirm the file is a candidate (not `findings.v1.json`), `domain` is `secrets`, values are `[REDACTED]`, and no Official Result keys exist.

## Compatibility
Cursor, Agent Arena operator
