#!/usr/bin/env python3
"""Run production comparison on broken-package-recovery for modal-kimi and groq-qwen."""

import json
import os
import sys
import time
from pathlib import Path

from agent_arena.target_library import get_target_library
from agent_arena.sandbox.client import FakeTransport, InternalClient
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
from agent_arena.providers import get_model_call_spec
from agent_arena import llm_client

def run_model_comparison(model_id: str, target_slug: str = "broken-package-recovery"):
    print(f"\n=======================================================")
    print(f"RUNNING TARGET: {target_slug} | MODEL: {model_id}")
    print(f"=======================================================")
    
    lib = get_target_library()
    bundle = lib.get_target(target_slug)
    if not bundle:
        raise SystemExit(f"Target {target_slug} not found")
        
    from agent_arena.target_library import compile_target_to_battle_config
    cfg = compile_target_to_battle_config(bundle)
    os.environ["ARENA_IN_SANDBOX"] = "1"
    os.environ["ARENA_PREVIEW"] = "0"
    
    transport = FakeTransport()
    transport.battle_status = "running"
    
    turn_counter = 0
    feedback_received_in_turns = []
    
    def model_post(path, body):
        nonlocal turn_counter
        if path == "/internal/model":
            turn_counter += 1
            base, style, key, model = get_model_call_spec(body["model_id"], None)
            msgs = body.get("messages") or []
            
            # Check if last user message contains tool output feedback
            for m in reversed(msgs):
                if m.get("role") == "user" and "Tool Output" in m.get("content", ""):
                    feedback_received_in_turns.append(turn_counter)
                    break
            
            resp = llm_client.chat_completion(
                base_url=base,
                auth_style=style,
                api_key=key,
                model=model,
                messages=msgs,
                tools=body.get("tools"),
                tool_choice=body.get("tool_choice"),
            )
            return {
                "content": resp.text if hasattr(resp, "text") else str(resp),
                "tool_calls": [c.model_dump() for c in resp.tool_calls] if hasattr(resp, "tool_calls") else [],
                "raw": getattr(resp, "raw", None),
            }
        if path == "/internal/round":
            transport.rounds.append(body)
            return {"ok": True}
        if path == "/internal/judge":
            return {
                "scores": {model_id: 100.0},
                "justifications": {model_id: "target evaluation"},
                "judge_model": "target-verifier",
            }
        return {"ok": True}
        
    transport.post = model_post
    client = InternalClient(transport)
    
    # Run AdvancedExecutor
    battle_id = f"cmp-{int(time.time())}-{model_id.replace(':', '-')}"
    from agent_arena.sandbox.executors.advanced_executor import fighter_roles
    fighters = fighter_roles(cfg)
    role_to_model = {r: model_id for r in fighters}
    
    executor = AdvancedExecutor()
    scores = executor.run_battle(
        battle_id=battle_id,
        format_config=cfg,
        model_ids=[model_id],
        round_visibility="isolated",
        timeout_seconds=360,
        role_to_model=role_to_model,
        client=client,
    )
    
    # Analyze rounds and traces
    telemetry = {
        "model_id": model_id,
        "target_slug": target_slug,
        "first_valid_tool_dialect": None,
        "native_calls": 0,
        "parsed_calls": 0,
        "repaired_calls": 0,
        "parse_failures": 0,
        "tool_execution_failures": 0,
        "edits": 0,
        "test_attempts": 0,
        "feedback_received_in_turns": feedback_received_in_turns,
        "skills_offered": [],
        "skills_loaded": [],
        "passed": False,
        "verifier_output": "",
        "total_turns": turn_counter,
    }
    
    for r in transport.rounds:
        artifact = r.get("artifact", "")
        trace = r.get("tool_trace") or []
        
        if "EXECUTOR_RESULT:" in artifact:
            try:
                res_payload = json.loads(artifact.split("EXECUTOR_RESULT:", 1)[1].strip())
                telemetry["passed"] = bool(res_payload.get("passed", False))
                telemetry["skills_offered"] = res_payload.get("skills_offered", [])
                telemetry["skills_loaded"] = res_payload.get("chosen_skills", [])
                telemetry["verifier_output"] = r.get("verification_log", res_payload.get("verification_log", ""))
            except Exception:
                pass
                
        for entry in trace:
            dialect = entry.get("dialect")
            status = entry.get("status")
            if dialect and not telemetry["first_valid_tool_dialect"]:
                telemetry["first_valid_tool_dialect"] = dialect
            if dialect == "openai_native":
                telemetry["native_calls"] += 1
            elif status == "parsed":
                telemetry["parsed_calls"] += 1
            elif status == "repaired":
                telemetry["repaired_calls"] += 1
            elif status == "failed":
                telemetry["parse_failures"] += 1
                
            tool_name = entry.get("tool") or (entry.get("call") or {}).get("name")
            if tool_name in ("write", "edit"):
                telemetry["edits"] += 1
            elif tool_name in ("test", "shell") and "test" in str(entry.get("call")):
                telemetry["test_attempts"] += 1
                
            if entry.get("execution_failed"):
                telemetry["tool_execution_failures"] += 1
                
    print("\n--- DETAILED TELEMETRY ---")
    print(f"Final Verdict: {'PASS' if telemetry['passed'] else 'FAIL'}")
    print(f"Skills Offered: {telemetry['skills_offered']}")
    print(f"Skills Loaded: {telemetry['skills_loaded']}")
    print(f"First Valid Tool Dialect: {telemetry['first_valid_tool_dialect']}")
    print(f"Native Calls: {telemetry['native_calls']}")
    print(f"Parsed Calls: {telemetry['parsed_calls']}")
    print(f"Repaired Calls: {telemetry['repaired_calls']}")
    print(f"Parse Failures: {telemetry['parse_failures']}")
    print(f"Tool Execution Failures: {telemetry['tool_execution_failures']}")
    print(f"Edits Made: {telemetry['edits']}")
    print(f"Test Attempts: {telemetry['test_attempts']}")
    print(f"Stdout/Stderr Feedback Fed Back: {'YES' if len(telemetry['feedback_received_in_turns']) > 0 else 'N/A'}")
    print(f"Final Verifier Output Snippet:\n{telemetry['verifier_output'][:400]}")
    
    return telemetry

if __name__ == "__main__":
    results = {}
    for m in ["host:modal-kimi", "host:groq-qwen"]:
        try:
            results[m] = run_model_comparison(m)
        except Exception as exc:
            print(f"Error running {m}: {exc}")
            import traceback
            traceback.print_exc()
