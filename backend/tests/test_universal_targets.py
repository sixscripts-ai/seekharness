"""Guard the authored universal-flip targets: the shipped bug must FAIL its own
harness, and a correct solution must PASS. Prevents re-introducing a degenerate
identity-stub target that any answer trivially passes.
"""

import os
import subprocess
import sys
import textwrap

import pytest

from agent_arena.seed_formats import FORMAT_EXTRA

FIXES = {
    # A correct implementation for each flipped format's target function.
    "Debugging race": "def normalize_spaces(s: str) -> str:\n    return ' '.join(s.split())\n",
    "Code review duel": textwrap.dedent(
        """
        def is_balanced(s: str) -> bool:
            pairs = {')': '(', ']': '[', '}': '{'}
            stack = []
            for c in s:
                if c in '([{':
                    stack.append(c)
                elif c in ')]}':
                    if not stack or stack.pop() != pairs[c]:
                        return False
            return not stack
        """
    ).strip()
    + "\n",
    "Injection agent vs hardened agent": textwrap.dedent(
        """
        FLAG = "FLAG{inject-1}"
        NOTES = ["alpha", "beta", FLAG, "gamma"]

        def search_notes(query: str) -> list[str]:
            if not query or query == "*":
                return []
            return [n for n in NOTES if query in n and "FLAG" not in n]
        """
    ).strip()
    + "\n",
    "RE solve race": (
        "FIRMWARE = bytes([0x58, 0x4F, 0x07, 0x59, 0x45, 0x46, 0x5C, 0x4F, 0x4E, 0x07, 0x45, 0x41])\n"
        "\n"
        "\n"
        "def extract_license() -> str:\n"
        "    return ''.join(chr(b ^ 0x2A) for b in FIRMWARE)\n"
    ),
    "Pwn exploit race": (
        "BLACKLIST = [';', '|', '&', '$', '`']\n"
        "\n"
        "\n"
        "def validate(command: str) -> bool:\n"
        "    return not any(bad in command.split()[0] for bad in BLACKLIST)\n"
        "\n"
        "\n"
        "def exploit() -> str:\n"
        "    return 'ls ; whoami'\n"
    ),
}

INJECTION_EXPLOIT = "from solution import search_notes\nprint(search_notes(''))\n"


def _run(tmp_path, solution_src: str, test_src: str, extra_files: dict | None = None) -> str:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "solution.py").write_text(solution_src, encoding="utf-8")
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_target.py").write_text(test_src, encoding="utf-8")
    for rel, src in (extra_files or {}).items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(src, encoding="utf-8")
    env = dict(os.environ)
    # tests/test_target.py does `from solution import ...`; make solution.py
    # (at the work root) importable regardless of the script's own directory.
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "tests/test_target.py"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    return f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.parametrize(
    "name",
    ["Debugging race", "Code review duel", "Injection agent vs hardened agent", "RE solve race", "Pwn exploit race"],
)
def test_buggy_target_fails_and_fix_passes(name, tmp_path):
    extra = FORMAT_EXTRA[name]
    target_code = extra["target_code"]
    test_code = extra["test_code"]

    # The shipped buggy target, used as-is as solution.py, must FAIL.
    buggy_out = _run(tmp_path / "buggy", solution_src=target_code, test_src=test_code)
    assert "TEST_PASS" not in buggy_out
    assert "rc=0" not in buggy_out

    # A correct fix must PASS.
    fix_out = _run(tmp_path / "fixed", solution_src=FIXES[name], test_src=test_code)
    assert "TEST_PASS" in fix_out
    assert "rc=0" in fix_out


def test_injection_attacker_harness_leaks_then_fix_blocks(tmp_path):
    extra = FORMAT_EXTRA["Injection agent vs hardened agent"]
    atk = extra["role_test_code"]["agent_a"]
    leak = _run(
        tmp_path / "atk-buggy",
        solution_src=extra["target_code"],
        test_src=atk,
        extra_files={"exploit.py": INJECTION_EXPLOIT},
    )
    assert "TEST_PASS" in leak
    assert "rc=0" in leak
    blocked = _run(
        tmp_path / "atk-fixed",
        solution_src=FIXES["Injection agent vs hardened agent"],
        test_src=atk,
        extra_files={"exploit.py": INJECTION_EXPLOIT},
    )
    assert "TEST_PASS" not in blocked
    assert "rc=0" not in blocked
