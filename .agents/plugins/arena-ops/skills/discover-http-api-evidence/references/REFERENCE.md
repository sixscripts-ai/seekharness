# HTTP API evidence notes

Candidate staging and Finding envelope: `../develop-finding/references/finding-contract.md`.
Single writer is `develop-finding`. Single validator is Evidence ingest. Do not add a second validator. Do not write `findings.v1.json`.

## Domain
`http_api` — HTTP/API contract (authn headers, CSRF, unsafe methods). Remediation only. No exploit steps.

## Staging
Write `scratch/candidates/http_api.json` (or an explicit operator path) with `candidate_schema: arena-finding-candidate-v1`.
