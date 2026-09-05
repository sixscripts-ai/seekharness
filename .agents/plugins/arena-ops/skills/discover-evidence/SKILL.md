---
name: discover-evidence
description: >
  Use this skill when an operator starts an off-battle Evidence review. Orchestrator only: run the domain-skill manifest, then hand off to develop-finding. Do not write findings.v1.json or Official Result fields.
license: MIT
compatibility: Cursor, Agent Arena operator
metadata:
  author: villain
  version: "1.0"
  targets: ["local", "cli"]
allowed-tools: "*"
---

# Discover Evidence

## Overview
Operator-only run manifest for Evidence discovery. Cursor door `/discover-evidence` lands here. This skill does not write Findings. Domain skills stage candidates; `develop-finding` is the sole writer of `findings.v1.json`. A Finding is Evidence only if a Battle later has that file. It is never an Official Result.

## Activation
Use when an operator invokes `/discover-evidence` or asks to review a codebase for structured risk claims. Off-battle default artifact path after handoff: `scratch/findings.v1.json` (or an explicit operator path). Do not add Format `artifacts.required`. Do not mount this on Fighters.

## Required Inputs
- Operator review scope (paths, Target id, or explicit output directory)
- Confirmation this is an operator review, not a Fighter skill

## Workflow
1. **Confirm seat**: Operator-mounted only. Stop if a Fighter would receive this review or Hidden Evaluator material.
2. **Run manifest** (in order; skip a domain only if the operator excludes it):
   1. `discover-auth-evidence`
   2. `discover-authz-evidence`
   3. `discover-secrets-evidence`
   4. `discover-http-api-evidence`
   5. `discover-sandbox-evidence`
   6. `discover-dependency-evidence`
3. **Collect candidates**: Expect `scratch/candidates/<domain>.json` (or the operator path). Do not rewrite them into `findings.v1.json`.
4. **Hand off**: Invoke `develop-finding` with the candidate set. That skill writes the artifact.
5. **State the limit**: Severity never sets passed, score, or winner. Do not write `exploit_evidence`.

## Output Contract
A run ledger listing which domain skills ran, which candidate files exist, and that `develop-finding` owns `scratch/findings.v1.json`. This skill writes no Finding envelope.

## Available Scripts
*(No scripts provided)*

## References
Read `../develop-finding/references/finding-contract.md` for the envelope, candidate shape, and ingest states (`absent` | `valid` | `invalid`).

## Safety and Permissions
Operator-mounted only. Fighters must not receive operator reviews or Hidden Evaluator material. No exploits, exploit PoCs, or attack procedures. Do not write Official Result fields (`passed`, `score`, `winner`).

## Failure Handling
If a domain skill cannot witness a claim, record SKIP/GAP and continue the manifest. Missing candidates are not a Fail-closed Outcome.

## Gotchas
- Run the manifest. Do not invent Findings or Official Result fields here.
- `audit-agent-run-evidence` and `clean-code-guard` keep their existing jobs. Do not reuse them as Finding writers.
- Distinct from `exploit_evidence`. Do not populate it.

## Examples
**Input**: Operator runs `/discover-evidence` on a local service.

**Action**: Execute the six domain skills, then `develop-finding`. Leave `findings.v1.json` to that writer.

## Validation
Confirm six domain skills were considered, only candidate files were staged by them, and this skill did not write `findings.v1.json`.

## Compatibility
Cursor, Agent Arena operator
