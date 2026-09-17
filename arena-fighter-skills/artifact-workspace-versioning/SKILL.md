---
name: artifact-workspace-versioning
description: >
  Build persistent progressive workspaces for coding agents, sandboxes, and multi-round
  battles. TRIGGER for artifact history, file snapshots, version selection, code diffs,
  workspace persistence, incremental edits, test-result attachment, restore/replay,
  process-tree restore into a workspace, or preventing agents from regenerating from
  scratch each round. Do not cap or truncate canonical artifacts.
license: MIT
metadata:
  author: sixscripts-ai
  version: "2.0.0"
  category: agent-workspaces
  tags: "artifacts,workspace,versions,diff,snapshots,progressive-code,history"
---

# Artifact Workspace Versioning

Treat an agent's previous working artifact as canonical state for the next iteration.

This skill owns versions and the mutable workspace. It must not disable `secure-code-execution`, `sandbox-runtime-engineer`, `realtime-execution-streaming`, `terminal-sandbox-ui`, or `battle-runtime-observability`.

## Canonical Model

Keep separate concepts for:

- workspace: current editable file tree of any size
- artifact_version: immutable submitted snapshot
- execution_result: build/test/runtime result attached to a version
- process_tree: persisted whole-process-tree record that can be saved, edited, restored, and terminated
- diff: derived change between versions
- opponent_artifact: approved read-only competitive context

Do not collapse all history into one transcript.

## Progressive Coding Workflow

Round 1 creates a baseline workspace. Later rounds should open the prior workspace, inspect feedback/opponent evidence, make targeted edits, verify them, and submit a new immutable version.

Preferred loop:

OBSERVE -> COMPARE -> PLAN -> PATCH -> TEST -> SUBMIT -> SCORE -> REPEAT

Do not restart from the original task unless the workspace is genuinely unsalvageable. Do not wipe the workspace on every command.

## Version Metadata

Every submitted version should capture:

- version number
- participant/model
- phase/round
- created_at
- file manifest or artifact body
- changed files
- additions/removals when available
- execution/test status
- score/judge feedback when available
- parent version
- process-tree reference when a tree was saved for that version

## Diff UX

Generate real line/file diffs rather than character-count heuristics. Preserve unchanged context, clearly show additions/removals, and handle file create/delete/rename where the artifact model supports it.

## Storage Rules

Use immutable version records and a mutable working copy. Filesystems and artifacts may be any size. Do not cap, truncate, or drop canonical files. If only excerpts are sent to the model, keep the full server-side artifact intact.

Trusted code has full workspace access inside its participant boundary: read, write, create, delete, and edit. Restore a saved process tree into that same workspace without creating a second writable tree for the same participant.

## Recovery

Reopening a battle should hydrate the latest canonical artifacts, version list, and saved process tree before attaching to the live stream. Reconnects must not create duplicate versions.

## Compatibility

- `secure-code-execution` forbids artifact size caps and requires per-participant isolation. Opponent visibility is approved artifacts only, never a shared writable workspace.
- `sandbox-runtime-engineer` persists and restores the process tree into this workspace. Do not discard that record on version submit.
- `realtime-execution-streaming` must replay version and file events without truncating bodies.
- `terminal-sandbox-ui` shows latest artifact, diff, and versions. Do not force the UI to concatenate history into one blob.
- `battle-runtime-observability` attaches traces to exact versions. Do not omit version IDs from execution results.

## Testing

Cover one version, 10+ versions, identical resubmission, multi-file snapshots, failed test before submit, reconnect duplication, version restore, large artifacts preserved in full, process-tree restore into the workspace, opponent visibility rules, and persistence after process restart.
