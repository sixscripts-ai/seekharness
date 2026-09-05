---
name: discover-sandbox-evidence
description: >
  Use this skill when an operator needs sandbox or Hidden Evaluator isolation remediations staged as a sandbox candidate for develop-finding, without writing findings.v1.json, Official Result fields, or Hidden Evaluator contents.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Discover Sandbox Evidence

## Overview
Operator-only review of sandbox and Hidden Evaluator isolation. Emits one `arena-finding-candidate-v1` record with domain `sandbox`. A Finding is a structured risk claim. When a Battle later ingests `findings.v1.json` it is Evidence. It is never an Official Result. Severity never sets passed, score, or winner. Follow `.cursor/skills/target-integrity-audit/SKILL.md`. Use synthetic markers only.

## Activation
Use when an operator asks for sandbox isolation remediations (Hidden Evaluator exposure, Builder/Breaker handoff, Target filesystem leaks). Off-battle: tell the operator these are candidates for `develop-finding`, which writes `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`.

## Required Inputs
- Review scope (Target bundle, sandbox paths, handoff allowlist)
- Output path: `scratch/candidates/sandbox.json` or an explicit operator path

## Workflow
1. **Scope Isolation**: Use the target-integrity-audit checklist. Do not paste Hidden Evaluator contents.
2. **Collect Witness**: Cite public paths and synthetic markers only. Remediation only.
3. **Draft Candidate**: Fill `arena-finding-candidate-v1` with domain `sandbox`.
4. **Stage File**: Write the candidate. Never write `findings.v1.json`.
5. **Hand Off**: Point the operator at `develop-finding`. Fighters must not receive this review or Hidden Evaluator material.

## Output Contract
Write only `scratch/candidates/sandbox.json` (or an explicit operator path). Shape: `candidate_schema`, `domain` (`sandbox`), `title`, `witness`, `affected_files`, `severity_hint`, `confidence_hint`, `remediation`. No Official Result keys. No `exploit_evidence`.

## Available Scripts
*(No scripts provided)*

## References
Read `references/REFERENCE.md` and `.cursor/skills/target-integrity-audit/SKILL.md`.

## Safety and Permissions
Operator-mounted only. Fighters must not receive operator reviews or Hidden Evaluator material. Use synthetic markers only. Do not write exploits, exploit PoCs, or attack procedures. Do not write Official Result fields (`passed`, `score`, `winner`) or `findings.v1.json`.

## Failure Handling
If isolation cannot be shown without Hidden Evaluator contents, stop and mark UNVERIFIED. Do not invent a candidate.

## Gotchas
- Hidden Evaluator, Builder workspace, and Breaker handoff stay Arena-owned. Do not copy private files into chat.
- Do not populate Official Result fields. Severity is a hint only.

## Examples
**Input**: Operator finds a starter symlink toward `tests/hidden` during a Target audit.

**Action**: Stage `scratch/candidates/sandbox.json` citing the public symlink and a synthetic marker. Remediate by removing the link. Do not paste Hidden Evaluator contents or write `findings.v1.json`.

## Validation
Confirm the file is a candidate (not `findings.v1.json`), `domain` is `sandbox`, no Hidden Evaluator contents, and no Official Result keys exist.

## Compatibility
Cursor, Agent Arena operator
