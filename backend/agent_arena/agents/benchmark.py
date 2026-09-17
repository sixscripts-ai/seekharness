"""Explicitly non-authoritative local development benchmark helper.

It reuses ``AdvancedExecutor`` to exercise an AgentConfig, but its transport
calls providers directly and does not create a persisted battle, sandbox token,
or trusted verifier record.  Its output must never be presented as an Arena
result or a complete runtime certification.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_arena.agents import AgentConfig, get_agent, get_agent_for_role
from agent_arena.providers import get_model_call_spec, reasoning_request_fields
from agent_arena import llm_client
from agent_arena.sandbox.client import InternalClient
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor
from agent_arena.target_library import (
    get_target_library,
    get_trusted_library_root,
    load_target_bundle,
    compile_target_to_battle_config,
)


@dataclass
class BenchmarkResult:
    target_id: str
    target_name: str
    agent_id: str
    agent_role: str
    model_id: str
    real_model: bool
    passed: bool
    terminal_state: str
    turns: int
    tool_calls: int
    tools_selected: Dict[str, int]
    duration_seconds: float
    verifier_details: Dict[str, Any]
    failure_category: Optional[str] = None
    tokens_prompt: int = 0
    tokens_completion: int = 0
    estimated_cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "agent_id": self.agent_id,
            "agent_role": self.agent_role,
            "model_id": self.model_id,
            "real_model": self.real_model,
            "passed": self.passed,
            "terminal_state": self.terminal_state,
            "turns": self.turns,
            "tool_calls": self.tool_calls,
            "tools_selected": self.tools_selected,
            "duration_seconds": round(self.duration_seconds, 2),
            "verifier_details": self.verifier_details,
            "failure_category": self.failure_category,
            "tokens": {
                "prompt": self.tokens_prompt,
                "completion": self.tokens_completion,
                "total": self.tokens_prompt + self.tokens_completion,
            },
            "estimated_cost_usd": round(self.estimated_cost_usd, 5),
        }


class RealModelTransport:
    """Direct-provider transport for an opt-in local benchmark only."""

    def __init__(self, user_id: str = "villain"):
        self.user_id = user_id
        self.rounds: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.model_calls_count = 0
        self.total_latency_ms = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.tool_calls_executed: Dict[str, int] = {}
        self.final_scores: Dict[str, Any] = {}
        self.verified_payloads: List[Dict[str, Any]] = []

    def post(self, path: str, payload: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        del timeout
        if path == "/internal/model":
            return self._handle_model(payload)
        if path == "/internal/round":
            self.rounds.append(payload)
            artifact = str(payload.get("artifact") or "")
            if artifact.startswith("{") and '"action"' in artifact:
                try:
                    action_data = json.loads(artifact)
                    action = action_data.get("action")
                    if action:
                        self.tool_calls_executed[action] = self.tool_calls_executed.get(action, 0) + 1
                except Exception:
                    pass
            return {"ok": True, "event_id": "real", "sequence": payload.get("sequence")}
        if path == "/internal/status":
            return {"status": "running"}
        if path == "/internal/judge":
            return {"scores": {}, "justifications": {}, "judge_model": "benchmark_harness"}
        if path == "/internal/verify":
            self.verified_payloads.append(payload)
            return {
                "ok": False,
                "passed": False,
                "error": "local benchmark transport does not run the trusted verifier",
            }
        if path == "/internal/finalize":
            self.final_scores = payload
            return {"ok": True, "status": payload.get("status", "completed")}

        return {"ok": True}

    def _handle_model(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        model_id = payload.get("model_id", "")
        messages = payload.get("messages", [])
        tools = payload.get("tools")
        max_tokens = payload.get("max_tokens", 4096)
        temperature = payload.get("temperature", 0.7)
        reasoning_effort = payload.get("reasoning_effort")
        tool_choice = payload.get("tool_choice")

        if model_id.startswith("scripted:"):
            return {
                "content": getattr(self, "model_canned", "DONE\n"),
                "tool_calls": [],
                "finish_reason": "stop",
                "latency_ms": 1,
            }

        base_url, auth_style, api_key, upstream_model = get_model_call_spec(model_id, self.user_id)

        t0 = time.perf_counter()
        resp = llm_client.chat_completion(
            base_url=base_url,
            auth_style=auth_style,
            api_key=api_key,
            model=upstream_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            provider_request_fields=reasoning_request_fields(
                model_id, reasoning_effort
            ),
            return_response_obj=True,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        self.model_calls_count += 1
        self.total_latency_ms += latency_ms

        content = getattr(resp, "text", str(resp or ""))
        tool_calls = getattr(resp, "native_tool_calls", [])
        finish_reason = getattr(resp, "raw_finish_reason", "stop")

        # Approximate token counting if provider didn't return raw usage
        prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        completion_chars = len(content) + sum(len(json.dumps(tc)) for tc in tool_calls)
        self.total_prompt_tokens += max(1, prompt_chars // 4)
        self.total_completion_tokens += max(1, completion_chars // 4)

        return {
            "content": content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "latency_ms": latency_ms,
        }


class AgentBenchmarkHarness:
    """Local development harness; never an Arena results producer."""

    def __init__(self, agent_id: str = "builder-v1", user_id: str = "villain"):
        self.agent = get_agent(agent_id) or get_agent_for_role(agent_id)
        if not self.agent:
            raise ValueError(f"Agent '{agent_id}' not found in registry")
        self.user_id = user_id

    def run_target(
        self,
        target_id: str,
        model_id: Optional[str] = None,
        timeout_seconds: int = 180,
    ) -> BenchmarkResult:
        """Run a direct-provider local experiment after explicit operator opt-in."""
        if os.environ.get("ARENA_ALLOW_DIRECT_BENCHMARK") != "1":
            raise RuntimeError(
                "Direct benchmark disabled. Set ARENA_ALLOW_DIRECT_BENCHMARK=1 "
                "to acknowledge an external, non-authoritative model call."
            )
        target_root = get_trusted_library_root()
        bundle = get_target_library(target_root).get_target(target_id)
        if bundle is None:
            # Try direct path
            candidate_path = Path(target_root) / target_id
            if candidate_path.is_dir():
                bundle = load_target_bundle(candidate_path)
        if bundle is None:
            raise FileNotFoundError(f"Target '{target_id}' not found in {target_root}")

        chosen_model = model_id or self.agent.model.preferred

        # Setup local execution environment flags
        os.environ["ARENA_IN_SANDBOX"] = "1"
        os.environ["ARENA_PREVIEW"] = "0"
        os.environ["ARENA_VERIFIER_ALLOW_INPROCESS"] = "1"

        transport = RealModelTransport(user_id=self.user_id)
        client = InternalClient(transport)
        executor = AdvancedExecutor()

        # Compile battle config
        is_bb = bundle.format == "builder_breaker"
        arena_size = 2 if is_bb else 1
        cfg = compile_target_to_battle_config(bundle, arena_size=arena_size)
        role_to_model = {}
        model_ids = []
        if is_bb:
            if self.agent.role == "breaker":
                active_role = "breaker"
                role_to_model = {"builder": "scripted:noop", "breaker": chosen_model}
                model_ids = ["scripted:noop", chosen_model]
                transport.model_canned = "DONE\n"
            else:
                active_role = "builder"
                role_to_model = {"builder": chosen_model, "breaker": "scripted:noop"}
                model_ids = [chosen_model, "scripted:noop"]
                transport.model_canned = "DONE\n"
            cfg["role_to_agent_id"] = {active_role: self.agent.agent_id}
        else:
            active_role = "fighter"
            cfg["role_to_agent_id"] = {active_role: self.agent.agent_id}
            role_to_model = {"fighter": chosen_model}
            model_ids = [chosen_model]
        if self.agent.budgets:
            cfg["max_tool_turns"] = self.agent.budgets.max_turns
            cfg["max_turns"] = self.agent.budgets.max_turns
            cfg["max_tool_steps"] = self.agent.budgets.max_steps
            cfg["max_steps"] = self.agent.budgets.max_steps
            if "limits" in cfg and isinstance(cfg["limits"], dict):
                cfg["limits"]["max_tool_turns"] = self.agent.budgets.max_turns
                cfg["limits"]["max_turns"] = self.agent.budgets.max_turns
                cfg["limits"]["max_tool_steps"] = self.agent.budgets.max_steps
                cfg["limits"]["max_steps"] = self.agent.budgets.max_steps

        t0 = time.time()
        battle_id = f"bench-{self.agent.agent_id}-{target_id}-{int(t0)}"

        try:
            scores = executor.run_battle(
                battle_id=battle_id,
                format_config=cfg,
                model_ids=model_ids,
                round_visibility="isolated",
                client=client,
                role_to_model=role_to_model,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            duration = time.time() - t0
            return BenchmarkResult(
                target_id=target_id,
                target_name=bundle.name,
                agent_id=self.agent.agent_id,
                agent_role=self.agent.role,
                model_id=chosen_model,
                real_model=True,
                passed=False,
                terminal_state="CRASHED",
                turns=transport.model_calls_count,
                tool_calls=sum(transport.tool_calls_executed.values()),
                tools_selected=transport.tool_calls_executed,
                duration_seconds=duration,
                verifier_details={"error": str(exc)},
                failure_category="runtime_crash",
            )

        duration = time.time() - t0

        # Parse results from transport rounds
        executor_results = []
        verifier_details: Dict[str, Any] = {}
        for r in transport.rounds:
            art = str(r.get("artifact") or "")
            if "EXECUTOR_RESULT:" in art:
                try:
                    payload = json.loads(art.split("EXECUTOR_RESULT:", 1)[1].strip())
                    executor_results.append(payload)
                except Exception:
                    pass
            if "TRUSTED_VERIFICATION:" in art:
                try:
                    payload = json.loads(art.split("TRUSTED_VERIFICATION:", 1)[1].strip())
                    verifier_details = payload
                except Exception:
                    pass

        # Target outcome analysis
        passed = False
        terminal_state = "UNKNOWN"
        failure_category = None
        role_turns = transport.model_calls_count
        role_tool_calls = sum(transport.tool_calls_executed.values())

        if executor_results:
            if self.agent.role == "breaker":
                primary_res = next(
                    (r for r in executor_results if r.get("role") == "breaker"),
                    executor_results[-1]
                )
            else:
                primary_res = next(
                    (r for r in executor_results if r.get("role") == "builder"),
                    executor_results[0]
                )
            passed = bool(primary_res.get("passed", False))
            terminal_state = str(primary_res.get("outcome", "UNKNOWN"))
            if primary_res.get("turns") is not None:
                role_turns = int(primary_res["turns"])
            if primary_res.get("steps") is not None:
                role_tool_calls = int(primary_res["steps"])
            if not passed:
                if terminal_state == "TURN_BUDGET_EXCEEDED":
                    failure_category = "turn_budget_exhausted"
                elif terminal_state == "PARSE_RECOVERY_EXHAUSTED":
                    failure_category = "parse_recovery_exhausted"
                elif terminal_state == "TEST_FAIL":
                    failure_category = "test_failure"
                else:
                    failure_category = terminal_state.lower()

        if verifier_details:
            if self.agent.role == "breaker":
                if verifier_details.get("breaker_passed") is not None:
                    passed = bool(verifier_details.get("breaker_passed"))
                elif "passed" in verifier_details:
                    passed = bool(verifier_details.get("passed", False))
                sem = verifier_details.get("breaker_semantic_evidence") or {}
                if not passed and sem.get("artifact_status") == "valid_breaker_artifact":
                    if sem.get("process_return_code") == 0:
                        failure_category = "trusted_semantic_unimplemented"
                    else:
                        failure_category = f"exploit_rc_{sem.get('process_return_code')}"
                elif not passed and sem.get("artifact_status") in ("missing_exploit_entrypoint", "no_breaker_artifact"):
                    failure_category = "missing_exploit_artifact"
            else:
                if verifier_details.get("builder_passed") is not None:
                    passed = bool(verifier_details.get("builder_passed"))
                elif "passed" in verifier_details:
                    passed = bool(verifier_details.get("passed", False))

        # Cost estimation: OpenRouter Qwen3-Coder is ~$0.0004 / 1k prompt, ~$0.0016 / 1k completion
        prompt_cost = (transport.total_prompt_tokens / 1000.0) * 0.0004
        comp_cost = (transport.total_completion_tokens / 1000.0) * 0.0016
        total_cost = prompt_cost + comp_cost

        return BenchmarkResult(
            target_id=target_id,
            target_name=bundle.name,
            agent_id=self.agent.agent_id,
            agent_role=self.agent.role,
            model_id=chosen_model,
            real_model=True,
            passed=passed,
            terminal_state=terminal_state,
            turns=role_turns,
            tool_calls=role_tool_calls,
            tools_selected=transport.tool_calls_executed,
            duration_seconds=duration,
            verifier_details=verifier_details,
            failure_category=failure_category if not passed else None,
            tokens_prompt=transport.total_prompt_tokens,
            tokens_completion=transport.total_completion_tokens,
            estimated_cost_usd=total_cost,
        )

    def run_benchmark(
        self,
        targets: List[str],
        model_id: Optional[str] = None,
        timeout_seconds: int = 180,
    ) -> List[BenchmarkResult]:
        """Run benchmark across multiple targets and print structured report."""
        results = []
        for tid in targets:
            print(f"\n[BENCHMARK] Running agent '{self.agent.agent_id}' on target '{tid}'...")
            res = self.run_target(tid, model_id=model_id, timeout_seconds=timeout_seconds)
            results.append(res)
            print(
                f"[RESULT] Target: {res.target_id} | Passed: {res.passed} | "
                f"Turns: {res.turns} | Tools: {res.tool_calls} | Time: {res.duration_seconds:.1f}s | "
                f"State: {res.terminal_state}"
            )
        return results


def print_benchmark_table(results: List[BenchmarkResult]) -> None:
    """Print formatted summary table of benchmark results."""
    print("\n" + "=" * 90)
    print(f"{'TARGET':<26} {'MODEL':<20} {'PASSED':<8} {'TURNS':<7} {'TOOLS':<7} {'TIME(s)':<8} {'STATUS':<12}")
    print("-" * 90)
    for r in results:
        status = r.terminal_state
        pass_str = "PASS" if r.passed else "FAIL"
        tools_summary = sum(r.tools_selected.values())
        print(
            f"{r.target_id:<26} {r.model_id:<20} {pass_str:<8} {r.turns:<7} "
            f"{tools_summary:<7} {r.duration_seconds:<8.1f} {status:<12}"
        )
    print("=" * 90 + "\n")


def main():
    parser = argparse.ArgumentParser(description="SeekHarness Agent Benchmark CLI")
    parser.add_argument("--agent", default="builder-v1", help="Agent identifier (e.g. builder-v1)")
    parser.add_argument(
        "--targets",
        default="authentication-gate,session-replay-defense,readme-lied",
        help="Comma-separated target identifiers",
    )
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--timeout", type=int, default=180, help="Timeout in seconds per target")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    args = parser.parse_args()
    target_list = [t.strip() for t in args.targets.split(",") if t.strip()]

    harness = AgentBenchmarkHarness(agent_id=args.agent)
    results = harness.run_benchmark(target_list, model_id=args.model, timeout_seconds=args.timeout)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print_benchmark_table(results)


if __name__ == "__main__":
    main()
