#!/usr/bin/env python3
"""
benchmark_runner.py - Runs deterministic benchmarks across Codex reasoning effort settings.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path


def run_benchmark(prompt: str, effort: str, cwd: Path) -> dict:
    cmd = [
        "codex", "exec", "--ephemeral", "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "-C", str(cwd),
        "-c", f'model_reasoning_effort="{effort}"',
        prompt
    ]

    start_time = time.time()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    wall_clock = time.time() - start_time

    events = []
    for line in proc.stdout.splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except Exception:
                pass

    # Extract metrics
    usage = {}
    tool_calls_count = 0
    tool_types = []
    final_response = ""
    first_tool_time = None
    turn_start_time = None
    native_exec = False
    errors = []

    for ev in events:
        ev_type = ev.get("type")
        if ev_type == "turn.started":
            turn_start_time = time.time()
        elif ev_type == "turn.completed":
            usage = ev.get("usage", {})
        elif ev_type == "error":
            errors.append(ev.get("message"))
        elif ev_type == "item.completed":
            item = ev.get("item", {})
            itype = item.get("type")
            if itype in ("tool_call", "command_execution", "exec_command"):
                tool_calls_count += 1
                tool_types.append(item.get("name") or itype)
                native_exec = True
            elif itype == "agent_message":
                final_response += item.get("text", "")
            elif itype == "text":
                final_response += item.get("text", "")
            # Check for messages inside content
            for c in item.get("content", []):
                if c.get("type") == "text":
                    final_response += c.get("text", "")

    return {
        "effort": effort,
        "exit_code": proc.returncode,
        "wall_clock_seconds": round(wall_clock, 2),
        "usage": {
            "input_tokens": usage.get("input_tokens", 0),
            "cached_input_tokens": usage.get("cached_input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "reasoning_output_tokens": usage.get("reasoning_output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        },
        "tool_calls_count": tool_calls_count,
        "tool_types": tool_types,
        "native_exec": native_exec,
        "response": final_response.strip(),
        "stderr": proc.stderr.strip()[:300],
        "errors": errors
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cwd = Path("/Users/villain/Developer/seekharness/agent-arena")
    res = run_benchmark(args.prompt, args.effort, cwd)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Effort: {res['effort']}")
        print(f"Wall clock: {res['wall_clock_seconds']}s")
        print(f"Tokens: {res['usage']}")
        print(f"Tool calls: {res['tool_calls_count']}")
        print(f"Response:\n{res['response']}")
