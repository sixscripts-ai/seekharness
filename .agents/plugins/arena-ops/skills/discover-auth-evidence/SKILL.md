---
name: discover-auth-evidence
description: >
  Use this skill when an operator needs identity, session, or login evidence staged as an auth candidate for develop-finding, without writing findings.v1.json or Official Result fields.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Discover Auth Evidence

## Overview
Operator-only review of Identity, session, and login gates. Emits one `arena-finding-candidate-v1` record with domain `auth`. A Finding is a structured risk claim. When a Battle later ingests `findings.v1.json` it is Evidence. It is never an Official Result. Severity never sets passed, score, or winner.

## Activation
Use when an operator asks for auth evidence (missing session checks, open login, Identity bypass). Off-battle: tell the operator these are candidates for `develop-finding`, which writes `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`.

## Required Inputs
- Review scope (paths, routes, Identity/session code)
- Output path: `scratch/candidates/auth.json` or an explicit operator path

## Workflow
1. **Scope Identity**: Locate login, session, and Identity gates only.
2. **Collect Witness**: Cite files and observed behavior. Remediation only.
3. **Draft Candidate**: Fill `arena-finding-candidate-v1` with domain `auth`.
4. **Stage File**: Write the candidate. Never write `findings.v1.json`.
5. **Hand Off**: Point the operator at `develop-finding`. Fighters must not receive this review.

## Output Contract
Write only `scratch/candidates/auth.json` (or an explicit operator path). Shape: `candidate_schema`, `domain` (`auth`), `title`, `witness`, `affected_files`, `severity_hint`, `confidence_hint`, `remediation`. No Official Result keys. No `exploit_evidence`.

## Available Scripts
*(No scripts provided)*

## References
Read `references/REFERENCE.md` for the Finding contract pointer and auth notes.

## Safety and Permissions
Operator-mounted only. Fighters must not receive operator reviews or Hidden Evaluator material. Remediation only. Do not write exploits, exploit PoCs, or attack procedures. Do not write Official Result fields (`passed`, `score`, `winner`) or `findings.v1.json`.

## Failure Handling
If Identity or session evidence is missing, do not invent a candidate. Report the gap and stop.

## Gotchas
- Domain is `auth`, not `authz`. Object-level access belongs in `discover-authz-evidence`.
- Do not populate Official Result fields. Severity is a hint only.

## Examples
**Input**: Operator reviews an admin route that returns 200 with no session cookie.

**Action**: Stage `scratch/candidates/auth.json` with witness on the missing Identity gate and a remediation to require a session. Do not write `findings.v1.json`.

## Validation
Confirm the file is a candidate (not `findings.v1.json`), `domain` is `auth`, and no Official Result keys exist.

## Compatibility
Cursor, Agent Arena operator
