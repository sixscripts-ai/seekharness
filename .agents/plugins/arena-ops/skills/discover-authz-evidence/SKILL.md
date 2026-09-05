---
name: discover-authz-evidence
description: >
  Use this skill when an operator needs authorization or object-level access evidence staged as an authz candidate for develop-finding, without writing findings.v1.json or Official Result fields.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Discover Authz Evidence

## Overview
Operator-only review of authorization and object-level access. Emits one `arena-finding-candidate-v1` record with domain `authz`. A Finding is a structured risk claim. When a Battle later ingests `findings.v1.json` it is Evidence. It is never an Official Result. Severity never sets passed, score, or winner.

## Activation
Use when an operator asks for authz evidence (IDOR, missing owner checks, role bypass). Off-battle: tell the operator these are candidates for `develop-finding`, which writes `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`.

## Required Inputs
- Review scope (paths, object IDs, Player/role checks)
- Output path: `scratch/candidates/authz.json` or an explicit operator path

## Workflow
1. **Scope Authorization**: Locate object-level and role gates only. Identity/login is `auth`.
2. **Collect Witness**: Cite files and observed access. Remediation only.
3. **Draft Candidate**: Fill `arena-finding-candidate-v1` with domain `authz`.
4. **Stage File**: Write the candidate. Never write `findings.v1.json`.
5. **Hand Off**: Point the operator at `develop-finding`. Fighters must not receive this review.

## Output Contract
Write only `scratch/candidates/authz.json` (or an explicit operator path). Shape: `candidate_schema`, `domain` (`authz`), `title`, `witness`, `affected_files`, `severity_hint`, `confidence_hint`, `remediation`. No Official Result keys. No `exploit_evidence`.

## Available Scripts
*(No scripts provided)*

## References
Read `references/REFERENCE.md` for the Finding contract pointer and authz notes.

## Safety and Permissions
Operator-mounted only. Fighters must not receive operator reviews or Hidden Evaluator material. Remediation only. Do not write exploits, exploit PoCs, or attack procedures. Do not write Official Result fields (`passed`, `score`, `winner`) or `findings.v1.json`.

## Failure Handling
If object-level access evidence is missing, do not invent a candidate. Report the gap and stop.

## Gotchas
- Domain is `authz`, not `auth`. Missing login/session is `discover-auth-evidence`.
- Do not populate Official Result fields. Severity is a hint only.

## Examples
**Input**: Operator reviews a Battle fetch that returns another Player's record by id with no owner check.

**Action**: Stage `scratch/candidates/authz.json` with witness on the missing object-level gate and a remediation to enforce ownership. Do not write `findings.v1.json`.

## Validation
Confirm the file is a candidate (not `findings.v1.json`), `domain` is `authz`, and no Official Result keys exist.

## Compatibility
Cursor, Agent Arena operator
