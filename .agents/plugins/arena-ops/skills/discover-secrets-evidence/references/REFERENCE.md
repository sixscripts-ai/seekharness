# Secrets evidence notes

Candidate staging and Finding envelope: `../develop-finding/references/finding-contract.md`.
Single writer is `develop-finding`. Single validator is Evidence ingest. Do not add a second validator. Do not write `findings.v1.json`.

## Domain
`secrets` — credential leakage. Never print secrets. Use `[REDACTED]` in witness and remediation. Never echo API keys.

## Staging
Write `scratch/candidates/secrets.json` (or an explicit operator path) with `candidate_schema: arena-finding-candidate-v1`.
