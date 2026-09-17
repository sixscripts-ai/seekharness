#!/usr/bin/env python3
"""
ship_task.py - Ships a bounded, self-contained coding task to Codex CLI.
Enforces:
1. Prompt word budget (<800 words).
2. Explicit boundary files.
3. Headless non-interactive codex exec execution.
4. Independent post-execution git diff & test suite verification.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


MAX_PROMPT_WORDS = 800


def count_words(text: str) -> int:
    return len(text.strip().split())


def check_codex_binary() -> tuple[bool, str]:
    try:
        proc = subprocess.run(["codex", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0:
            return True, proc.stdout.strip()
        return False, proc.stderr.strip()
    except Exception as e:
        return False, str(e)


def get_git_state(cwd: Path) -> set[str]:
    proc = subprocess.run(["git", "status", "--porcelain=v1"], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    files = set()
    for line in proc.stdout.splitlines():
        if line.strip():
            files.add(line[3:].strip().split(" -> ")[-1])
    return files


def run_codex_task(prompt: str, cwd: Path) -> tuple[int, str, str]:
    cmd = [
        "codex", "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C", str(cwd),
        prompt
    ]
    proc = subprocess.run(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def inspect_git_diff(before_files: set[str], after_files: set[str], allowed_files: list[str]) -> tuple[bool, list[str]]:
    # New files introduced during task
    new_files = after_files - before_files
    if not allowed_files:
        return True, list(new_files)

    out_of_bounds = [f for f in new_files if f not in allowed_files]
    return (len(out_of_bounds) == 0), out_of_bounds


def run_verification_test(test_cmd: str, cwd: Path) -> tuple[bool, str]:
    if not test_cmd:
        return True, "No verification test specified."

    proc = subprocess.run(test_cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    passed = (proc.returncode == 0)
    output = proc.stdout if passed else (proc.stdout + "\n" + proc.stderr)
    return passed, output.strip()


def main():
    parser = argparse.ArgumentParser(description="Ship bounded task to Codex CLI and independently verify output.")
    parser.add_argument("--task", help="Direct task instructions for Codex")
    parser.add_argument("--prompt-file", help="Path to text/markdown file containing task prompt")
    parser.add_argument("--allowed-files", help="Comma-separated list of files Codex is permitted to modify")
    parser.add_argument("--test-cmd", help="Deterministic test command to run for independent verification")
    parser.add_argument("--dry-run", action="store_true", help="Validate prompt budget and config without invoking Codex")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    if not (repo_root / "backend").exists():
        repo_root = Path.cwd()

    # 1. Resolve prompt
    prompt_text = ""
    if args.prompt_file:
        pf = Path(args.prompt_file)
        if not pf.exists():
            print(f"Error: Prompt file '{args.prompt_file}' not found", file=sys.stderr)
            sys.exit(1)
        prompt_text = pf.read_text(encoding="utf-8")
    elif args.task:
        prompt_text = args.task
    else:
        print("Error: Must provide either --task or --prompt-file", file=sys.stderr)
        sys.exit(1)

    words = count_words(prompt_text)
    if words > MAX_PROMPT_WORDS:
        print(f"Error: Prompt budget exceeded ({words} words > max {MAX_PROMPT_WORDS})", file=sys.stderr)
        sys.exit(1)

    # 2. Check codex health
    healthy, version_info = check_codex_binary()
    if not healthy:
        print(f"Error: Codex CLI is not available or unhealthy: {version_info}", file=sys.stderr)
        sys.exit(1)

    allowed_list = [f.strip() for f in args.allowed_files.split(",")] if args.allowed_files else []

    report = {
        "status": "VALIDATED",
        "word_count": words,
        "max_words": MAX_PROMPT_WORDS,
        "codex_version": version_info,
        "allowed_files": allowed_list,
        "test_cmd": args.test_cmd
    }

    if args.dry_run:
        report["dry_run"] = True
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"[DRY-RUN] Prompt passed budget check: {words}/{MAX_PROMPT_WORDS} words.")
            print(f"[DRY-RUN] Codex CLI: {version_info}")
            print(f"[DRY-RUN] Allowed files: {allowed_list or 'Any'}")
            print(f"[DRY-RUN] Test command: {args.test_cmd or 'None'}")
        return

    # Snapshot git state before
    before_state = get_git_state(repo_root)

    # 3. Invoke Codex CLI
    print(f"Shipping bounded task ({words} words) to Codex CLI...")
    retcode, c_out, c_err = run_codex_task(prompt_text, repo_root)

    # Snapshot git state after
    after_state = get_git_state(repo_root)

    # 4. Check boundaries
    bounded, violations = inspect_git_diff(before_state, after_state, allowed_list)

    # 5. Independent Verification
    verified, test_output = run_verification_test(args.test_cmd, repo_root) if args.test_cmd else (True, "Skipped")

    overall_success = (retcode == 0) and bounded and verified
    report["execution"] = {
        "exit_code": retcode,
        "within_bounds": bounded,
        "boundary_violations": violations if not bounded else [],
        "tests_verified": verified,
        "test_output": test_output[:300] if test_output else "",
        "overall_success": overall_success
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print("==================================================")
    print("           CODEX TASK EXECUTION REPORT            ")
    print("==================================================")
    status_label = "SUCCESS" if overall_success else "FAILED"
    print(f"Result           : {status_label}")
    print(f"Codex Exit Code  : {retcode}")
    print(f"Within Bounds    : {'YES' if bounded else 'VIOLATED (' + str(violations) + ')'}")
    print(f"Tests Verified   : {'PASS' if verified else 'FAIL'}")
    if not verified:
        print(f"Test Details     : {test_output[:200]}")
    print("==================================================")

    if not overall_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
