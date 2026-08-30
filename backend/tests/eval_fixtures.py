"""Temporary private evaluator packages for hermetic tests.

Hermetic tests must never read the real `targets/evaluators/` tree: it is
gitignored, so a clean public clone does not have it, and its contents are
benchmark secrets. Every helper here builds synthetic material in a temp dir.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_HIDDEN = {"test_hidden.py": "def test_ok():\n    assert True\n"}

_PY_HIDDEN_PLACEHOLDER = (
    "# Synthetic hermetic-test placeholder. Not the real hidden suite.\n"
    "def test_placeholder():\n"
    "    assert True\n"
)
_JS_HIDDEN_PLACEHOLDER = (
    "// Synthetic hermetic-test placeholder. Not the real hidden suite.\n"
    "import assert from 'node:assert/strict';\n"
    "import test from 'node:test';\n"
    "test('placeholder', () => assert.equal(1, 1));\n"
)


def write_private_evaluator(
    eval_root: Path,
    target_id: str,
    *,
    hidden: dict[str, str] | None = None,
    reference: dict[str, str] | None = None,
    extra: dict[str, str] | None = None,
) -> Path:
    dest = eval_root / target_id
    files = DEFAULT_HIDDEN if hidden is None else hidden
    for rel, text in files.items():
        path = dest / "tests" / "hidden" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel, text in (reference or {}).items():
        path = dest / "reference" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel, text in (extra or {}).items():
        path = dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return dest


def point_evaluators(monkeypatch, eval_root: Path) -> None:
    monkeypatch.setenv("ARENA_EVALUATOR_DIR", str(eval_root))


def reset_target_library_cache() -> None:
    """Drop the process-wide registry so a temp library root cannot leak."""
    import agent_arena.target_library as target_library

    target_library._GLOBAL_REGISTRY = None


def write_synthetic_evaluator_overlays(library_root: Path, eval_root: Path) -> Path:
    """Give every public target a synthetic private evaluator package.

    `load_target_bundle` fails closed when a target declares a `hidden_command`
    but has no private package. Tests that exercise the real public library
    therefore need *an* overlay; they must not need the real one. Bodies are
    placeholders — no test executes a real hidden suite.
    """
    import yaml

    library_root = Path(library_root)
    eval_root = Path(eval_root)
    eval_root.mkdir(parents=True, exist_ok=True)
    if not library_root.is_dir():
        return eval_root

    for target_dir in sorted(library_root.iterdir()):
        manifest = target_dir / "target.yaml"
        if not target_dir.is_dir() or not manifest.is_file():
            continue
        try:
            raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        hidden_command = str(
            (raw.get("verification") or {}).get("hidden_command") or ""
        )
        if not hidden_command.strip():
            continue
        if ".test.js" in hidden_command or "node" in hidden_command:
            hidden = {"edge.test.js": _JS_HIDDEN_PLACEHOLDER}
        else:
            hidden = {"test_hidden.py": _PY_HIDDEN_PLACEHOLDER}
        write_private_evaluator(
            eval_root, str(raw.get("id") or target_dir.name), hidden=hidden
        )
    return eval_root


_SOLO_MANIFEST = """
schema_version: 1
id: {tid}
name: Synthetic Solo Reference
category: software-engineering
difficulty: novice
format: solo
runtime: python311
description: Synthetic solo target whose private reference solution passes verification.
tags:
- python
objectives:
- Make ledger totals correct.
workspace:
  starter_dir: starter
  visible_tests_dir: tests/visible
  hidden_tests_dir: tests/hidden
  reference_dir: reference
  protected_paths: []
  handoff_allowlist: []
network: false
verification:
  visible_command: python3 -m pytest tests/visible -q
  hidden_command: python3 -m pytest tests/hidden -q
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 8
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
"""

SOLO_BROKEN_SOURCE = "def total(items):\n    return 0\n"
SOLO_REFERENCE_SOURCE = "def total(items):\n    return sum(items)\n"

_SOLO_VISIBLE_TEST = (
    "from ledger import total\n\n\n"
    "def test_total_sums():\n"
    "    assert total([1, 2]) == 3\n"
)
_SOLO_HIDDEN_TEST = (
    "from ledger import total\n\n\n"
    "def test_hidden_total():\n"
    "    assert total([5, 5]) == 10\n\n\n"
    "def test_hidden_empty():\n"
    "    assert total([]) == 0\n"
)


def write_solo_reference_target(
    library_root: Path,
    eval_root: Path,
    target_id: str = "synthetic-solo-reference",
) -> Path:
    """Public solo target plus a private overlay whose reference passes.

    Replaces test dependence on real reference solutions: the starter fails the
    visible suite and the synthetic reference passes visible + hidden.
    """
    target = Path(library_root) / target_id
    (target / "starter").mkdir(parents=True, exist_ok=True)
    (target / "tests" / "visible").mkdir(parents=True, exist_ok=True)
    (target / "target.yaml").write_text(
        _SOLO_MANIFEST.format(tid=target_id), encoding="utf-8"
    )
    (target / "starter" / "ledger.py").write_text(
        SOLO_BROKEN_SOURCE, encoding="utf-8"
    )
    (target / "tests" / "visible" / "test_ledger.py").write_text(
        _SOLO_VISIBLE_TEST, encoding="utf-8"
    )
    write_private_evaluator(
        Path(eval_root),
        target_id,
        hidden={"test_hidden_ledger.py": _SOLO_HIDDEN_TEST},
        reference={"ledger.py": SOLO_REFERENCE_SOURCE},
    )
    return target


_BB_MANIFEST = """
schema_version: 1
id: {tid}
name: Synthetic Builder Breaker Reference
category: cybersecurity
difficulty: advanced
format: builder_breaker
runtime: python311
description: Synthetic builder/breaker target with a private hardened reference.
tags:
- python
- authorization
objectives:
  builder:
  - Reject forged admin tokens.
  breaker:
  - Prove an authorization bypass with exploit.py.
workspace:
  starter_dir: starter
  visible_tests_dir: tests/visible
  hidden_tests_dir: tests/hidden
  reference_dir: reference
  protected_paths: []
  handoff_allowlist:
  - app.py
network: false
verification:
  visible_command: python3 -m pytest tests/visible -q
  hidden_command: python3 -m pytest tests/hidden -q
  ranked_requires_hidden_pass: true
limits:
  max_tool_steps: 12
  exec_timeout_seconds: 60
safety:
  scope: synthetic-local-only
  real_targets: false
  network_required: false
"""

BB_VULNERABLE_SOURCE = "def is_admin(token):\n    return True\n"
BB_REFERENCE_SOURCE = 'def is_admin(token):\n    return token == "admin-token"\n'

_BB_VISIBLE_TEST = (
    "from app import is_admin\n\n\n"
    "def test_admin_token_allowed():\n"
    '    assert is_admin("admin-token") is True\n'
)
_BB_HIDDEN_TEST = (
    "from app import is_admin\n\n\n"
    "def test_forged_token_rejected():\n"
    '    assert is_admin("forged") is False\n'
)


def write_builder_breaker_reference_target(
    library_root: Path,
    eval_root: Path,
    target_id: str = "synthetic-bb-reference",
) -> Path:
    """Public builder/breaker target plus a private hardened reference overlay.

    Starter passes visible tests but fails the hidden security suite; the
    synthetic reference passes both.
    """
    target = Path(library_root) / target_id
    (target / "starter").mkdir(parents=True, exist_ok=True)
    (target / "tests" / "visible").mkdir(parents=True, exist_ok=True)
    (target / "target.yaml").write_text(
        _BB_MANIFEST.format(tid=target_id), encoding="utf-8"
    )
    (target / "starter" / "app.py").write_text(
        BB_VULNERABLE_SOURCE, encoding="utf-8"
    )
    (target / "tests" / "visible" / "test_app.py").write_text(
        _BB_VISIBLE_TEST, encoding="utf-8"
    )
    write_private_evaluator(
        Path(eval_root),
        target_id,
        hidden={"test_security.py": _BB_HIDDEN_TEST},
        reference={"app.py": BB_REFERENCE_SOURCE},
    )
    return target
