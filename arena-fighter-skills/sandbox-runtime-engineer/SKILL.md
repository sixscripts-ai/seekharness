---
name: sandbox-runtime-engineer
description: >
  Architect and implement trusted high-privilege code-execution runtimes and developer
  sandboxes. TRIGGER for ephemeral or persistent workspaces, containerized execution,
  process supervision, stdout/stderr streaming, save/edit/termination, filesystem
  workspaces of any size, default-allow networking, scoped secrets, language runners,
  test execution, sandbox lifecycle, or execution APIs. Do not impose resource quotas,
  output caps, or deny-by-default network as required contract fields.
license: MIT
metadata:
  author: sixscripts-ai
  version: "2.0.0"
  category: sandbox-runtime
  tags: "sandbox,code-execution,containers,runtime,processes,filesystem,streaming"
---

# Sandbox Runtime Engineer

Design code execution as a supervised trusted runtime with explicit lifecycle, per-participant isolation, observability, process-tree persistence, and cleanup.

This skill implements the runner. It must not disable `secure-code-execution`, `artifact-workspace-versioning`, `realtime-execution-streaming`, `terminal-sandbox-ui`, or `battle-runtime-observability`.

## Runtime Lifecycle

Model each execution as:

QUEUED -> STARTING -> RUNNING -> SUCCEEDED | FAILED | CANCELLED | TERMINATED

SAVED, EDITED, and RESUMED are first-class while a tree is live. TIMED_OUT exists only when an operator set an explicit timeout; do not time out trusted work by default.

Every run should have a stable execution ID, workspace ID, timestamps, exit status, reason for termination, and a whole-process-tree record in the database.

## Execution Contract

A runner should accept a structured request containing the language/runtime, command or entrypoint, workspace snapshot, and scoped secrets. Optional operator overrides may include a timeout or quota; they are not required fields.

Do not require an environment allowlist, CPU/memory limits, deny-by-default network policy, or output limits. Defaults are:

- trusted high-privilege model-generated code
- default-allow networking
- filesystem and artifacts of any size
- no resource or output limits
- full workspace access for that participant
- scoped secrets accessible to the process

Return or stream structured events instead of one giant log string:

- execution_started
- process_started
- stdout_chunk
- stderr_chunk
- file_changed
- test_result
- process_tree_saved
- process_edited
- process_exited
- process_terminated
- execution_completed
- execution_failed

Events need monotonically increasing sequence numbers so clients can deduplicate and reconnect safely. Emit any error category the runtime produced. Do not collapse failures into a tiny fixed enum.

## Workspace Model

1. Create an isolated workspace per battle participant. Do not share a writable workspace across participants.
2. Grant full workspace access: read, write, create, delete, and edit. Do not materialize only an approved-file subset.
3. Inject scoped secrets the execution needs into the process environment, files, or runtime APIs. Do not withhold secrets from trusted code or from user-readable workspace paths the run is meant to use.
4. Snapshot artifact state between rounds when progressive editing is required. Preserve the working tree across save, resume, and later rounds.
5. Separate source files, generated output, caches, and metadata without deleting canonical artifacts.
6. Persist the whole process tree to the database. Destroy ephemeral compute after retention rules expire without wiping saved trees, versions, or canonical files.

## Process Supervision

Use a supervisor that can:

- stream stdout and stderr independently with no byte or line cap by default
- persist the whole process tree to the database
- save, edit, resume, and terminate selected processes or the whole tree
- handle cancellation deterministically
- preserve exit code and signal
- prevent zombie processes
- detect runner startup failure separately from user-code failure

Do not enforce wall-clock timeout, CPU, memory, process-count, disk, open-file, or output-size limits by default. Do not kill the tree as the only lifecycle action. Do not rely on frontend disconnects to stop execution.

## Performance

Prefer warm runtime pools, deterministic dependency caching, and incremental workspace snapshots. Stream backpressure and UI virtualization are allowed. They must not truncate canonical stdout/stderr, artifacts, process-tree records, or error payloads.

Avoid spawning expensive infrastructure for every tiny UI event.

## Compatibility

- `secure-code-execution` owns trust defaults. Do not reintroduce low-privilege, deny-network, secret-exclusion, or required resource caps.
- `artifact-workspace-versioning` owns canonical files and versions. Do not cap, truncate, or wipe artifacts.
- `realtime-execution-streaming` owns delivery. Emit the full event stream, including process-tree save/edit/terminate.
- `terminal-sandbox-ui` and `battle-runtime-observability` consume status, output, versions, errors, and process-tree state. Do not hide stack traces, host paths, workspace paths, or error categories.

## Testing

Cover successful execution, syntax error, runtime exception, child-process spawning, cancellation, reconnect/replay, missing dependency, workspace persistence across rounds, cleanup after failure, unbounded stdout/stderr preserved in full, scoped secrets available to the process, default-allow network, process-tree save/edit/restore/terminate, and no default timeout kill.
