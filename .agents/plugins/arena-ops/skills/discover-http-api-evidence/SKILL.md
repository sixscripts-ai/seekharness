---
name: discover-http-api-evidence
description: >
  Use this skill when an operator needs HTTP or API contract evidence (authn headers, CSRF, unsafe methods) staged as an http_api candidate for develop-finding, without writing findings.v1.json or Official Result fields.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Discover HTTP API Evidence

## Overview
Operator-only review of HTTP/API contracts: authn headers, CSRF, and unsafe methods. Emits one `arena-finding-candidate-v1` record with domain `http_api`. A Finding is a structured risk claim. When a Battle later ingests `findings.v1.json` it is Evidence. It is never an Official Result. Severity never sets passed, score, or winner.

## Activation
Use when an operator asks for HTTP/API evidence (missing authn headers, CSRF gaps, unsafe verbs). Off-battle: tell the operator these are candidates for `develop-finding`, which writes `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`.

## Required Inputs
- Review scope (routes, handlers, client calls)
- Output path: `scratch/candidates/http_api.json` or an explicit operator path

## Workflow
1. **Scope Contract**: Locate HTTP methods, authn headers, and CSRF controls only.
2. **Collect Witness**: Cite files and observed contract gaps. Remediation only. No exploit steps.
3. **Draft Candidate**: Fill `arena-finding-candidate-v1` with domain `http_api`.
4. **Stage File**: Write the candidate. Never write `findings.v1.json`.
5. **Hand Off**: Point the operator at `develop-finding`. Fighters must not receive this review.

## Output Contract
Write only `scratch/candidates/http_api.json` (or an explicit operator path). Shape: `candidate_schema`, `domain` (`http_api`), `title`, `witness`, `affected_files`, `severity_hint`, `confidence_hint`, `remediation`. No Official Result keys. No `exploit_evidence`.

## Available Scripts
*(No scripts provided)*

## References
Read `references/REFERENCE.md` for the Finding contract pointer and HTTP/API notes.

## Safety and Permissions
Operator-mounted only. Fighters must not receive operator reviews or Hidden Evaluator material. Remediation only. Do not write exploits, exploit PoCs, or attack procedures. Do not write Official Result fields (`passed`, `score`, `winner`) or `findings.v1.json`.

## Failure Handling
If the HTTP/API gap cannot be witnessed from code or traces, do not invent a candidate. Report the gap and stop.

## Gotchas
- Identity/session gates are `auth`. Object-level access is `authz`. This skill is the HTTP contract only.
- Do not populate Official Result fields. Severity is a hint only.

## Examples
**Input**: Operator reviews a state-changing POST with no CSRF token and no authn header.

**Action**: Stage `scratch/candidates/http_api.json` with witness on the missing header/CSRF check and a remediation to require both. Do not write exploit steps or `findings.v1.json`.

## Validation
Confirm the file is a candidate (not `findings.v1.json`), `domain` is `http_api`, and no Official Result keys exist.

## Compatibility
Cursor, Agent Arena operator
