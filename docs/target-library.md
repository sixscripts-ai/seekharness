# Agent Arena Target Library Architecture & Integration Guide

The Agent Arena Target Library provides standardized, reproducible, multi-file benchmark targets for autonomous coding and cybersecurity agents.

---

## 1. Directory Structure

Target packages reside under `targets/library/<target_id>/`:

```
targets/library/<target_id>/
├── target.yaml          # Canonical YAML specification
├── README.md            # Mission brief and description
├── starter/             # Base repository materialized for the agent
└── tests/visible/       # Tests mounted in workspace for agent feedback

targets/evaluators/<target_id>/   # private; gitignored except .gitkeep
├── tests/hidden/        # Evaluator-only tests
└── reference/           # Gold-standard reference solution
```

---

## 2. Manifest Schema (`target.yaml`)

```yaml
schema_version: 1
id: "broken-package-recovery"
name: "Broken Package Recovery"
category: "debugging"
difficulty: "novice"
format: "solo"
runtime: "node22"
description: "Repair a corrupted Node package manifest and restore lockfile integrity."
tags:
  - npm
  - package.json
  - nodejs
objectives:
  - "Fix syntax and dependency errors in package.json"
  - "Ensure npm test passes"
workspace:
  starter_dir: "starter"
  visible_tests_dir: "tests/visible"
  hidden_tests_dir: "tests/hidden"
  reference_dir: "reference"
  protected_paths:
    - "tests/hidden/**"
  handoff_allowlist: []
network: false
verification:
  visible_command: "npm test"
  hidden_command: "pytest tests/hidden/test_integrity.py"
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 18
  exec_timeout_seconds: 360
safety:
  scope: "synthetic-local-only"
  real_targets: false
  network_required: false
```

---

## 3. Evaluator Separation & Security Model

To prevent benchmark tampering and reward hacking:

1. **Strict File Partitioning**:
   - `starter_files` and `visible_test_files` are copied into `work_{role}`.
   - `hidden_test_files` and `reference_files` load only from `$ARENA_EVALUATOR_DIR/<id>` or `targets/evaluators/<id>`, stay in backend memory, and are never written to the agent's filesystem.
2. **Path Traversal Guards**:
   - All manifest paths and file requests are validated against regex `^[A-Za-z0-9_.*-][A-Za-z0-9_./*-]*$`.
   - Any path with `..`, leading `/`, or symlink pointing outside target root raises `TargetSecurityError`.
3. **Builder → Breaker Handoffs**:
   - In `builder_breaker` formats, only files matching `workspace.handoff_allowlist` are captured.
   - The Builder workspace is purged before launching the Breaker workspace.
4. **Deterministic Integrity Hashes**:
   - `manifest_hash`: SHA-256 of `target.yaml`.
   - `starter_hash`: Deterministic tree hash of starter files.
   - `hidden_hash`: Deterministic tree hash of hidden test suite.
5. **Private Evaluator Delivery (production)**:
   - Evaluator packages ship in the named Modal Volume `arena-evaluators`, never baked into an image and never attached to a fighter sandbox.
   - The trusted backend function mounts it read-only at `/opt/arena-evaluators` and is the only place `ARENA_EVALUATOR_DIR` is set.
   - Because that mount is readable by path regardless of environment, target battles refuse same-host runners (`run_in_process`, `ARENA_USE_MOCK`) whenever private evaluator storage is present, and must use the isolated sandbox.

---

## 4. Target Catalog API

### `GET /targets`
Returns a list of public target summaries.

**Sample Response:**
```json
[
  {
    "id": "broken-package-recovery",
    "name": "Broken Package Recovery",
    "description": "Repair a corrupted Node package manifest...",
    "category": "debugging",
    "difficulty": "novice",
    "format": "solo",
    "runtime": "node22",
    "tags": ["npm", "package.json", "nodejs"],
    "version": "1.0.0",
    "visible_test_count": 1,
    "hidden_test_count": 2,
    "handoff_required": false,
    "verification_type": "visible+hidden",
    "network": false,
    "manifest_hash": "a1b2c3..."
  }
]
```

### `GET /targets/{target_id}`
Returns full public target details including public file list and mission objectives (zero hidden tests).

---

## 5. Battle Creation with Target Bundles

Battles can be created with an explicit `target_id`:

```json
POST /battles
{
  "format_id": "format-1",
  "target_id": "broken-package-recovery",
  "model_ids": ["deepseek-r1", "claude-3-7-sonnet"],
  "arena_size": 2,
  "timeout_seconds": 600
}
```

When `target_id` is supplied, the target manifest hash and runtime configuration are frozen on the battle record.
