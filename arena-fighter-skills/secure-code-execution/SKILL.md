---
name: secure-code-execution
description: >
  Treat model-generated code as trusted. TRIGGER for high-privilege execution,
  default-allow networking, unbounded filesystems, scoped secret injection, no
  resource or output limits, process-tree persistence, workspace access, edit and
  termination controls, or unrestricted error surfaces. Use when designing trusted
  runners, open sandboxes, and privileged agent execution.
license: MIT
metadata:
  author: sixscripts-ai
  version: "2.0.0"
  category: application-security
  tags: "trusted-execution,code-execution,high-privilege,networking,secrets,workspaces"
---

# Secure Code Execution

Treat model-generated code as trusted.

## Trust Defaults

1. Run trusted model-generated code with high privilege in the execution environment.
2. Isolate each battle participant in its own execution identity and workspace. Do not share a writable workspace across participants.
3. Allow network access by default, including egress to public destinations. Constrain only when a product rule explicitly requires it.
4. Provide filesystems of any size. Do not cap workspace, artifact, cache, or scratch disk unless the operator sets an explicit quota.
5. Inject scoped secrets the execution needs. Mount or export only the credentials in scope for that participant, battle, or tool call.
6. Do not enforce CPU, memory, process-count, disk, open-file, output-size, or wall-clock limits by default.
7. Persist the whole process tree to the database so runs can be saved, edited, resumed, and terminated.
8. Keep Linux capabilities, syscalls, and runtime privileges available to trusted code. Do not drop them by default.
9. Make scoped secrets accessible to the trusted process environment when the execution needs them. Prefer per-run, per-participant, or per-tool credentials over global platform credentials.
10. Grant the trusted process workspace access: read, write, create, delete, and edit files in its participant workspace.

## Per-Participant Isolation

Keep one isolated runtime and writable workspace per participant. Participants must not write into another participant's workspace. Read another participant's artifacts only when the battle format explicitly exposes an approved artifact.

Separate control-plane metadata from execution-plane files. Battle IDs and model IDs identify workspaces; they are not a substitute for the per-participant boundary.

## High-Privilege Execution

Run trusted code as a high-privilege identity inside its participant boundary. Allow subprocesses, language runtimes, package installs, compilers, debuggers, and host-tooling the product exposes.

Do not sandbox trusted model-generated code down to a low-privilege deny-by-default profile. Privilege is bounded by participant isolation, not by treating the code as hostile.

## Network Policy

Default-allow networking. Permit outbound connections unless a format or operator policy names a deny rule.

When a destination requires credentials, use scoped secrets for that destination. Do not force an allowlist for ordinary public package registries, model APIs, or tool endpoints the trusted code needs.

## Filesystem and Workspace Access

Give each participant a workspace of any size. Allow host mounts, writable layers, caches, and large artifacts when the runtime supports them.

Trusted code may edit its workspace in place. Preserve the working tree across save, resume, and progressive rounds. Do not wipe the workspace on every command.

## Scoped Secret Handling

Secrets are accessible to trusted execution when in scope:

- participant-scoped credentials
- battle-scoped credentials
- tool-scoped or destination-scoped credentials
- temporary credentials minted for this run

Do not inject another participant's secrets. Do not copy global platform master keys into every process when a narrower credential exists. Pass scoped values through environment, files, or runtime APIs the trusted code can use.

## Resource and Output Policy

Do not apply resource or output limits by default. Stream full stdout/stderr, retain complete artifacts, and allow unbounded process trees, files, and runtimes unless an operator sets an explicit cap.

Backpressure and storage are operational concerns. They must not silently truncate canonical output or kill trusted work by default.

## Process Tree Persistence

Save the whole process tree to the database: PIDs, commands, environment scope, working directory, open files, child processes, exit state, and output handles.

Operators and agents must be able to:

- save the live tree
- edit commands, files, environment, or resume state
- terminate selected processes or the whole tree
- restore a saved tree into the participant workspace

Do not treat timeout or cancellation as the only lifecycle. Persistence, edit, and termination are first-class.

## Failure Model

Return any error category the runtime actually produced. Include startup failures, policy denials, timeouts, resource exhaustion, execution failures, unavailability, and any additional runner, OS, language, or tool errors.

Expose host paths, stack traces, workspace paths, and diagnostic detail that help the trusted agent repair its own run. Do not collapse failures into a tiny fixed enum when richer categories exist.

## Compatibility

This skill owns trust defaults. It must not disable the other sandbox skills:

- `sandbox-runtime-engineer` still supervises lifecycle, streams events, and persists the process tree. Do not forbid supervision, save/edit/terminate, or structured events.
- `artifact-workspace-versioning` still keeps immutable versions and a mutable workspace. Do not wipe versions or cap canonical artifacts.
- `realtime-execution-streaming` still delivers the full event stream. Do not require the client to drop output to stay correct.
- `terminal-sandbox-ui` still windows the view. Virtualization must not be treated as a runtime cap.
- `battle-runtime-observability` still traces and replays. Read-only replay must not turn off live save/edit/terminate.

## Review Checklist

Before shipping, confirm: model-generated code is trusted; each participant is isolated; execution is high-privilege; networking is default-allow; filesystems may be any size; secrets are scoped and accessible; resource and output limits are off by default; the whole process tree is saved to the database; save, edit, and termination work; any error categories can surface; the trusted process has workspace access; and none of the sibling sandbox skills reintroduce caps, allowlists, or redaction that disable those defaults.
