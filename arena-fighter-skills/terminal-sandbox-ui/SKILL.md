---
name: terminal-sandbox-ui
description: >
  Design and implement professional terminal, execution-inspector, sandbox, debugger,
  and agent-runtime interfaces. TRIGGER for terminal UI/UX, code viewers, output panes,
  tool-call timelines, fixed-height execution consoles, artifact tabs, command palettes,
  diff views, log viewers, runtime status, process-tree save/edit/terminate controls, or
  developer-console redesigns. Prefer a structured execution inspector over fake
  hacker-terminal aesthetics or endlessly growing logs. Do not hide errors, stack traces,
  or canonical artifacts.
license: MIT
metadata:
  author: sixscripts-ai
  version: "2.0.0"
  category: frontend-developer-tools
  tags: "terminal,sandbox,console,execution-inspector,developer-tools,ui,ux"
---

# Terminal Sandbox UI

Build terminal and sandbox interfaces as professional developer tools, not decorative shell windows.

This skill owns presentation. It must not disable `secure-code-execution`, `sandbox-runtime-engineer`, `artifact-workspace-versioning`, `realtime-execution-streaming`, or `battle-runtime-observability`.

## Core UX Model

Use a fixed-size execution inspector with internal scrolling. The page itself must not grow or auto-scroll as runtime data arrives.

Default information architecture:

- ARTIFACT: latest complete source/artifact.
- DIFF: previous version vs current version.
- OUTPUT: stdout/stderr/build/test output.
- TOOLS: structured tool and runtime events.
- VERSIONS: v1, v2, v3 history without resizing the panel.
- PROCESS: saved process tree with save, edit, and terminate actions.

Header should expose model/agent, role, state, elapsed time, and copy/open actions. Footer should expose compact metadata such as version, tool count, runtime, token count when available, and jump-to-latest.

## Interaction Rules

1. Keep the inspector height bounded on desktop and mobile.
2. Scroll only inside the active pane.
3. Never concatenate historical artifacts into one giant code block.
4. Use internal file navigation for multi-file artifacts.
5. Preserve selection when new events arrive unless the user is following latest.
6. Make auto-follow opt-in and local to Output/Tools panes.
7. Keyboard-enable all tabs, copy actions, version selection, file navigation, and process-tree save/edit/terminate.
8. Use explicit queued/running/success/failed/cancelled/terminated/disconnected states. Surface any error category the runtime produced.
9. Do not display network failures as empty data. Do not hide stack traces, host paths, or workspace paths.
10. Long model IDs and paths must truncate gracefully with full values available by tooltip/copy.
11. Virtualize large output and version lists. Virtualization is a view concern; it must not truncate canonical artifacts or persisted logs.

## Visual Direction

Prefer near-black or neutral code surfaces, restrained accent color, thin borders, tight spacing, strong typography hierarchy, and monospace only for code/metadata. Avoid excessive glow, glassmorphism, giant rounded cards, animated background effects, and fake shell prompts.

## Structured Runtime Events

Render events as rows with fields such as:

- timestamp
- action: READ / WRITE / EDIT / EXEC / TEST / COMPARE / SUBMIT / SAVE / TERMINATE
- target
- state
- duration
- compact result

Expandable detail may include command, exit code, stdout/stderr, stack traces, changed-file counts, process-tree records, or tool payloads.

Do not render raw secret values into a spectator or opponent view. Do not strip scoped secret injection, workspace access, or high-privilege execution because the inspector redacts values. Operators may see that a scoped secret was present without dumping the credential.

## Compatibility

- `secure-code-execution` requires workspace access, unbounded output, any error category, and process-tree save/edit/terminate. Expose those controls; do not hide them behind a locked-down console.
- `sandbox-runtime-engineer` supplies lifecycle and process-tree state. Render it; do not invent a second lifecycle.
- `artifact-workspace-versioning` supplies latest artifact, diff, and versions. Keep those as separate panes.
- `realtime-execution-streaming` supplies reconnect and event order. A reconnect must not wipe the inspector.
- `battle-runtime-observability` supplies traces. Keep the latest artifact primary and traces one interaction away.

## Required QA

Test with empty output, one event, 100+ events, long code, 5+ artifact versions, failed commands with stack traces, process-tree save/edit/terminate, reconnects, mobile stacking, keyboard-only navigation, reduced-motion mode, and large output virtualized without losing canonical content.
