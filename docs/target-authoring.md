# Target Authoring Toolkit

Developer toolkit for creating and validating Agent Arena targets.  All commands
consume the authoritative production loader (`target_library.load_target_bundle`
and `sandbox.executors._command_guard`) – there is no second parallel validator.

Library root resolves as ` $ARENA_TARGETS_DIR ` → `/opt/arena-targets` →
`targets/library` (same as production).  Override with `--library-root`.

## Installation

No new dependency is required (PyYAML, stdlib).  Canonical invocation is:

```bash
backend/.venv/bin/python -m agent_arena.targets_cli --help
```

A console-script entry point `arena-targets` is registered in
`backend/pyproject.toml` (`[project.scripts] arena-targets = "agent_arena.targets_cli:main"`).
After an editable install it is available as `arena-targets`:

```bash
uv pip install -e backend   # or: pip install -e backend
arena-targets --help
```

Until installed, use `python -m agent_arena.targets_cli`.  The shell alias
`alias arena-targets='backend/.venv/bin/python -m agent_arena.targets_cli'` is
an equivalent shortcut without installation.

## 1. Create – scaffold a new target

```bash
# dry-run: show what would be created
arena-targets scaffold my-new-target --dry-run

# create into targets/drafts/<id>/  (default)
arena-targets scaffold my-new-target

# choose destination and metadata
arena-targets scaffold my-new-target --dest /tmp/my-new-target \
  --category systems --difficulty advanced --format solo --runtime python311

# JSON for automation
arena-targets scaffold my-new-target --dry-run --json

# overwrite an existing draft
arena-targets scaffold my-new-target --dest ./targets/drafts/my-new-target --force
```

Generated skeleton:

```
<target-id>/
  target.yaml              # manifest – edit category/difficulty/format/runtime as needed
  README.md                # mission overview placeholder
  starter/                 # broken project the fighter repairs
  tests/visible/           # visible tests (fighter sees)
  tests/hidden/            # hidden tests (evaluator only)
  reference/               # reference solution (never shipped to fighter)
```

**No hidden solutions are generated.**  Placeholders use `assert True`; you
must implement real starter/hidden/reference content.

IDs must be lowercase kebab-case `^[a-z0-9][a-z0-9-]*$` (max 64 chars).

## 2. Structure – what a bundle contains

```
targets/library/<id>/
  target.yaml              # required; sha256 of this file is manifest_hash
  README.md
  starter/                 # mounted as fighter workspace
  tests/visible/           # visible verification tests
  tests/hidden/            # hidden evaluator tests (never exposed to fighter)
  reference/               # evaluator-only reference (never exposed)
```

Manifest fields (all authoritative; validated by `load_target_bundle`):

| Field | Notes |
|-------|-------|
| `id`, `name`, `description` | `id` must equal folder name |
| `category` | e.g. `software-engineering`, `cybersecurity`, `systems`, `data-sql`, `ctf`, `agent-security`, `agent-tool-use`, `cybersecurity-data` |
| `difficulty` | `novice` / `general` / `advanced` / `expert` |
| `format` | `solo` / `builder_breaker` / `ctf` / `adversarial_agent` |
| `runtime` | `python311`, `python311-fastapi`, `python311-sqlite`, `node22`, `linux-gcc-make` |
| `tags`, `objectives` | objectives supports flat list or `{builder:[], breaker:[]}` |
| `workspace.{starter_dir, visible_tests_dir, hidden_tests_dir, reference_dir, protected_paths, handoff_allowlist}` | paths are validated against traversal & absolute-path escapes |
| `verification.{visible_command, hidden_command}` | blocked by the same `_command_guard` as fighter tool calls (`..`, `~`, `$HOME`, absolute paths, `curl`/`wget` unless `network:true`, SSRF) |
| `limits`, `safety`, `network`, `version` | `version` defaults to `1.0.0` (semver) |

Hashes: `manifest_hash = sha256(target.yaml utf-8)`; partition hashes are
deterministic over sorted paths+contents (`compute_bundle_hash`).

## 3. Validate

```bash
arena-targets validate authentication-gate
arena-targets validate --all
arena-targets validate --all --json   # CI-friendly
```

Runs the authoritative `load_target_bundle` for each bundle and prints
`PASS`/`FAIL`.  `validate --all` exits `0` only if every bundle is valid;
otherwise non-zero (CI-gate suitable).

## 4. Test – safe smoke checks

```bash
arena-targets test my-new-target
arena-targets test my-new-target --json
```

Safe checks only (no hidden solutions exposed, no destructive payloads outside
the sandbox):

- bundle loads
- starter / visible / hidden dirs present
- `visible_command` / `hidden_command` not blocked by `_command_guard`
- runtime is known
- starter / visible file counts

Note printed after each run: “Not tested: hidden expected outputs, reference
solutions, destructive execution outside sandbox” – full verification only runs
inside the sandbox.

## 5. Library doctor

```bash
arena-targets doctor
arena-targets doctor --json
```

Library-wide consistency beyond per-manifest validation:

- duplicate target IDs / conflicting versions
- malformed semver
- missing required files / dirs
- manifest hash mismatch
- absolute paths / `..` traversal in `protected_paths` / `handoff_allowlist` / file keys
- missing verifier files (not yet, but flagged as empty commands)
- invalid `difficulty` / `format` / `runtime` (closed vocabularies -> `ERROR`)
- `category`: unknown values are `WARNING` (categories are EXTENSIBLE); empty or
  malformed (regex `^[a-z0-9][a-z0-9-]*$`) -> `ERROR`. The current 8 known
  categories do not freeze tomorrow's catalog.
- duplicated / empty tags, non-lowercase tags
- malformed handoff contracts (e.g. `builder_breaker` with empty `handoff_allowlist`)
- blocked verification commands (same guard as production)

Severity: `ERROR` (must fix), `WARNING` (should fix, unknown-but-safe category,
inconsistent vocabulary, empty starter, non-lowercase tag), `INFO` (optional
reference dir missing). Exits `1` if any `ERROR`, otherwise `0`.

## 6. Other commands

```bash
arena-targets list
arena-targets list --json

arena-targets inspect authentication-gate
arena-targets inspect authentication-gate --json  # safe metadata only

arena-targets hash authentication-gate
arena-targets hash authentication-gate --json     # canonical sha256 of target.yaml

arena-targets stats
arena-targets stats --json
```

`inspect` never prints hidden test bodies or reference solutions – only counts
and hashes.

## 7. Publish – moving to production

A draft in `targets/drafts/<id>/` becomes production when:

1. `arena-targets validate <id>` → PASS
2. `arena-targets test <id>` → PASS
3. `arena-targets doctor` → 0 errors
4. `arena-targets hash <id>` matches the bundle’s `manifest_hash`
5. You manually move the directory to `targets/library/<id>/` and open a PR

CI (see below) will re-validate every target on the PR.

## 8. CI integration

For PRs touching `targets/library/**`, run:

```bash
backend/.venv/bin/python -m agent_arena.targets_cli validate --all
backend/.venv/bin/python -m agent_arena.targets_cli doctor
```

Both are CI-friendly: human-readable by default, `--json` for machine
consumption, stable keys, meaningful exit codes (`0` clean, `1` failure,
`2` usage error), no secrets in output.

Example GitHub Actions step (`.github/workflows/targets.yml`):

```yaml
name: targets
on:
  pull_request:
    paths: ['targets/library/**', 'backend/agent_arena/target_library.py']
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r backend/requirements.txt || pip install pyyaml
      - run: python -m agent_arena.targets_cli validate --all
      - run: python -m agent_arena.targets_cli doctor
```

Do not modify deployment workflows; this workflow only gates target PRs.

## 9. Workflow for target #11

```bash
# 1. scaffold
arena-targets scaffold my-target-11 --category systems --difficulty general --format solo --runtime python311

# 2. edit  (implement starter project, visible/hidden tests, reference, README)
$EDITOR targets/drafts/my-target-11/target.yaml
$EDITOR targets/drafts/my-target-11/starter/...

# 3. validate
arena-targets validate my-target-11 --library-root targets/drafts

# 4. smoke test
arena-targets test my-target-11 --library-root targets/drafts

# 5. library doctor (copy draft into a temp library or move to library)
arena-targets doctor --library-root targets/drafts

# 6. inspect / hash
arena-targets inspect my-target-11 --library-root targets/drafts
arena-targets hash my-target-11 --library-root targets/drafts

# 7. review → move to production
mv targets/drafts/my-target-11 targets/library/my-target-11
arena-targets validate --all
arena-targets doctor
git add targets/library/my-target-11
```

Production runtime behavior is unchanged – targets remain immutable,
repository-backed, and loaded only from `targets/library`.

## Reused production code

- `target_library.load_target_bundle`, `TargetLibraryRegistry`, `validate_safe_relative_path`, `compute_bundle_hash`, `get_default_library_root`, `TargetManifestError`, `TargetSecurityError` (public wrappers; private names retained for backward compatibility)
- `sandbox.executors._command_guard.command_block_reason`
- Hashing and registry semantics are identical to the Modal image mount (`ARENA_TARGETS_DIR` → `/opt/arena-targets`)
