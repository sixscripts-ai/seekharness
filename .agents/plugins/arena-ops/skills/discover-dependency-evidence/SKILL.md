---
name: discover-dependency-evidence
description: >
  Use this skill when an operator needs dependency-risk remediations staged as a dependency candidate for develop-finding, without writing findings.v1.json, Official Result fields, or attack procedures.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Discover Dependency Evidence

## Overview
Operator-only review of dependency risk. Emits one `arena-finding-candidate-v1` record with domain `dependency`. A Finding is a structured risk claim. When a Battle later ingests `findings.v1.json` it is Evidence. It is never an Official Result. Severity never sets passed, score, or winner.

## Activation
Use when an operator asks for dependency remediations (unpinned packages, abandoned pins, known-risk versions). Off-battle: tell the operator these are candidates for `develop-finding`, which writes `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`.

## Required Inputs
- Review scope (lockfiles, manifests, install scripts)
- Output path: `scratch/candidates/dependency.json` or an explicit operator path

## Workflow
1. **Scope Dependencies**: Locate manifests and lockfiles only.
2. **Collect Witness**: Cite package, version, and file. Remediation only.
3. **Draft Candidate**: Fill `arena-finding-candidate-v1` with domain `dependency`.
4. **Stage File**: Write the candidate. Never write `findings.v1.json`.
5. **Hand Off**: Point the operator at `develop-finding`. Fighters must not receive this review.

## Output Contract
Write only `scratch/candidates/dependency.json` (or an explicit operator path). Shape: `candidate_schema`, `domain` (`dependency`), `title`, `witness`, `affected_files`, `severity_hint`, `confidence_hint`, `remediation`. No Official Result keys. No `exploit_evidence`.

## Available Scripts
*(No scripts provided)*

## References
Read `references/REFERENCE.md` for the Finding contract pointer and dependency notes.

## Safety and Permissions
Operator-mounted only. Fighters must not receive operator reviews or Hidden Evaluator material. Remediation only. Do not write exploits, exploit PoCs, or attack procedures. Do not write Official Result fields (`passed`, `score`, `winner`) or `findings.v1.json`.

## Failure Handling
If the lockfile or manifest is missing, do not invent a candidate. Report the gap and stop.

## Gotchas
- Name the package and the remediation (pin, upgrade, remove). Do not describe how to exploit it.
- Do not populate Official Result fields. Severity is a hint only.

## Examples
**Input**: Operator reviews an unpinned HTTP client in `pyproject.toml` with a known-risk range.

**Action**: Stage `scratch/candidates/dependency.json` with witness on the unpinned range and a remediation to pin a patched version. Do not write exploit steps or `findings.v1.json`.

## Validation
Confirm the file is a candidate (not `findings.v1.json`), `domain` is `dependency`, and no Official Result keys exist.

## Compatibility
Cursor, Agent Arena operator
