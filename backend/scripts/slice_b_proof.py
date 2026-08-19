"""Slice B proof: real-model execution loop evidence (run from backend/).

Drives AdvancedExecutor.run_battle in-process with a REAL model transport
(OpenRouter free tier), preserves the temp workspaces for hashing, and
emits a JSON evidence report covering: model calls, tool action logs,
EXECUTOR_RESULT records, workspace file hashes, and the feedback loop
(earlier tool output appearing in later model context).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

BACKEND = str(Path(__file__).resolve().parents[1])
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from agent_arena import llm_client  # noqa: E402
from agent_arena.config import settings  # noqa: E402
from agent_arena.providers import OPENROUTER_BASE  # noqa: E402
from agent_arena.sandbox.client import FakeTransport, InternalClient  # noqa: E402
from agent_arena.sandbox.executors import advanced_executor as adv_mod  # noqa: E402
from agent_arena.sandbox.executors.advanced_executor import AdvancedExecutor  # noqa: E402
from agent_arena.seed_formats import ALL_FORMATS  # noqa: E402

MODEL = os.environ.get("SLICE_B_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")
FIXED_ROOT = Path("/tmp/arena-sliceb-workspace")


class RealModelTransport(FakeTransport):
    """FakeTransport shell whose /internal/model path calls a real provider."""

    def _post_locked(self, path, json):
        self.calls.append((path, json))
        if path == "/internal/model":
            try:
                content = llm_client.chat_completion(
                    base_url=OPENROUTER_BASE,
                    auth_style="openrouter",
                    api_key=settings().get("HOST_OPENROUTER_KEY") or "",
                    model=MODEL,
                    messages=list(json.get("messages") or []),
                    max_tokens=int(json.get("max_tokens") or 1024),
                )
            except Exception as exc:
                content = f"TOOL shell cmd='echo MODEL_ERROR {type(exc).__name__}'\nDONE"
            return {"content": content or ""}
        return super()._post_locked(path, json)


class FixedTemporaryDirectory:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        FIXED_ROOT.mkdir(parents=True, exist_ok=True)
        return FIXED_ROOT

    def __exit__(self, *args):
        return False


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def main() -> dict:
    import shutil

    shutil.rmtree(FIXED_ROOT, ignore_errors=True)
    os.environ["ARENA_IN_SANDBOX"] = "1"
    os.environ["ARENA_PREVIEW"] = "0"
    cfg = next(c for c in ALL_FORMATS if c["name"] == "Debugging race")
    cfg = {**cfg, "max_tool_turns": 3, "max_tool_steps": 20, "pick_per_battle": 1}
    starter = {"TARGET.md": cfg["target_code"], "tests/test_target.py": cfg["test_code"]}

    transport = RealModelTransport()
    transport.battle_status = "running"
    transport.judge_result = {
        "scores": {"m-a": 5.0, "m-b": 5.0},
        "justifications": {},
        "judge_model": "slice-b-stub",
    }
    client = InternalClient(transport)

    adv_mod.tempfile.TemporaryDirectory = FixedTemporaryDirectory
    t0 = time.time()
    scores = AdvancedExecutor().run_battle(
        battle_id="slice-b-proof",
        format_config=cfg,
        model_ids=["m-a", "m-b"],
        round_visibility="isolated",
        timeout_seconds=420,
        role_to_model={"player_a": "m-a", "player_b": "m-b"},
        client=client,
    )
    elapsed = round(time.time() - t0, 1)

    workspace: dict = {}
    for role in ("player_a", "player_b"):
        d = FIXED_ROOT / f"work_{role}"
        files = {}
        if d.is_dir():
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.stat().st_size < 30000:
                    files[str(p.relative_to(d))] = hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()[:16]
        workspace[role] = files

    results = []
    actions = []
    emission_order = []
    for r in transport.rounds:
        artifact = r.get("artifact") or ""
        if "EXECUTOR_RESULT:" in artifact:
            payload = json.loads(artifact.split("EXECUTOR_RESULT:", 1)[1].strip())
            results.append(
                {k: v for k, v in payload.items() if k in (
                    "model_id", "role", "phase", "outcome", "passed", "steps",
                    "tool_errors", "parse_errors", "artifact_checks",
                    "executor_version", "skill_read_ok",
                )}
            )
        if r.get("event_type") == "action_log":
            try:
                d = json.loads(artifact)
            except Exception:
                continue
            actions.append(
                {
                    "model_id": r.get("model_id"),
                    "action": d.get("action"),
                    "state": d.get("state"),
                    "result_head": (d.get("result") or "")[:120],
                }
            )
        if r.get("event_type") in ("action_log", "artifact") and r.get("model_id"):
            emission_order.append(
                {"model_id": r.get("model_id"), "artifact": artifact, "phase": r.get("phase")}
            )

    reqs = [c[1] for c in transport.calls if c[0] == "/internal/model"]
    request_contexts = []
    for idx, req in enumerate(reqs):
        all_text = "".join(m.get("content", "") for m in (req.get("messages") or []))
        request_contexts.append(
            {
                "model_id": req.get("model_id"),
                "index": idx,
                "prompt_tail": all_text[-400:],
                "has_prior": "Prior:" in all_text,
            }
        )
    feedback = []
    for idx, req in enumerate(reqs):
        mid = req.get("model_id")
        all_text = "".join(m.get("content", "") for m in (req.get("messages") or []))
        for prior in emission_order:
            snippet = prior["artifact"][:80]
            if (
                prior["model_id"] == mid
                and len(snippet) >= 20
                and snippet in all_text
            ):
                feedback.append(
                    {
                        "model_id": mid,
                        "request_index": idx,
                        "prior_artifact_head": snippet[:60],
                    }
                )
                break

    report = {
        "model": MODEL,
        "scores_returned": scores,
        "elapsed_s": elapsed,
        "model_calls": len(reqs),
        "starter_hashes": {k: _hash(v) for k, v in starter.items()},
        "workspace_files": workspace,
        "executor_results": results,
        "action_logs": actions[:24],
        "feedback_loop_matches": feedback,
        "request_contexts": request_contexts,
    }
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, default=str))
