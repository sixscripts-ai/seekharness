"""Trusted Target Verifier: executes verification in a hardened environment.

Security guarantees:
1. Strict environment sanitization: strips all host secrets, API keys, credentials, tokens, and backend URLs.
2. Isolated temporary workspace: builds clean directory structure and mounts partitions safely.
3. Evaluator separation: fighter code never receives hidden tests; verifier runs in its own workspace.
4. Asymmetric Builder vs. Breaker evaluation: scores both builder functional correctness/defense and breaker exploit proof.
"""

from __future__ import annotations

import os
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .sandbox.executors._command_guard import command_block_reason
from .breaker_isolation import BreakerExecution, run_breaker_isolated
from .target_library import TargetBundle, compute_bundle_hash, validate_safe_relative_path

# Fighter-authored pytest/Python config must never become the verifier harness.
_HARNESS_BASENAMES = frozenset(
    {
        "conftest.py",
        "conftest.pyc",
        "pytest.ini",
        ".pytest.ini",
        "pytest.toml",
        "pyproject.toml",
        "tox.ini",
        "setup.cfg",
        "setup.py",
        "sitecustomize.py",
        "usercustomize.py",
        "noxfile.py",
    }
)

_ARENA_PYTEST_INI = """[pytest]
cache_dir = .arena-pytest-cache
norecursedirs = .* __pycache__
"""

_ALLOWED_ENV_VARS = {
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "TERM",
    "USER",
    "LOGNAME",
    "SHELL",
    "TZ",
}

_STRIP_KEY_PATTERNS = re.compile(
    r"(KEY|SECRET|TOKEN|PASSWORD|PASSWD|AUTH|APPWRITE|MODAL|INTERNAL|BEARER|CREDENTIAL|PRIVATE|DATABASE|URL)",
    re.IGNORECASE,
)


def _blocked_submission_path(rel_path: str) -> bool:
    """Return True if a fighter-supplied file path must not be written.

    Blocks absolute paths, '..' traversal, evaluator partitions, the entire
    trusted tests/ tree, and pytest/Python harness configuration files.
    """
    clean_rel = str(rel_path).replace("\\", "/").strip()
    if not clean_rel or clean_rel.startswith("/"):
        return True
    parts = [p for p in clean_rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return True
    if not parts:
        return True
    if parts[0].lower().startswith("reference"):
        return True
    if parts[0].lower() == "tests":
        return True
    if parts[-1].lower() in _HARNESS_BASENAMES:
        return True
    return False


def _write_arena_pytest_harness(work: pathlib.Path) -> pathlib.Path:
    """Install the Arena-owned pytest config. Overwrites any fighter/starter copy."""
    ini_path = work / "pytest.ini"
    ini_path.write_text(_ARENA_PYTEST_INI, encoding="utf-8")
    # Empty trusted conftest so a leftover fighter file cannot occupy this name.
    (work / "conftest.py").write_text(
        "# Arena-owned verifier conftest. Fighters cannot supply pytest hooks.\n",
        encoding="utf-8",
    )
    return ini_path


def _is_pytest_command(command: str) -> bool:
    return bool(re.search(r"\bpytest\b", str(command or "")))


def _harden_pytest_command(command: str, *, ini_path: pathlib.Path, root: pathlib.Path) -> str:
    """Force Arena pytest config even when the manifest invokes pytest.

    Flags stay relative to `root` so the command guard does not reject
    absolute paths.
    """
    if not _is_pytest_command(command):
        return command
    try:
        ini_rel = ini_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        ini_rel = "pytest.ini"
    extra = f" --noconftest -c {ini_rel} --rootdir=. -p no:cacheprovider"
    return f"{command.rstrip()} {extra}"


def _build_hardened_env(work: pathlib.Path, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a strictly sanitized, minimal environment without host credentials or leaked secrets."""
    clean_env: dict[str, str] = {}
    for k, v in os.environ.items():
        if k in _ALLOWED_ENV_VARS and not _STRIP_KEY_PATTERNS.search(k):
            clean_env[k] = v

    # Make the current interpreter's bin dir findable so verification commands
    # like `pytest` resolve on dev machines where they live in the venv.
    bin_dir = os.path.dirname(sys.executable)
    if bin_dir:
        current_path = clean_env.get("PATH") or ""
        parts = [p for p in current_path.split(os.pathsep) if p]
        if bin_dir not in parts:
            parts.insert(0, bin_dir)
        clean_env["PATH"] = os.pathsep.join(parts)

    clean_env["PYTHONPATH"] = str(work)
    clean_env["ARENA_ROOT"] = str(work)
    clean_env["ARENA_WORKDIR"] = str(work)
    clean_env["ARENA_FLAG"] = "FLAG{tinyshop-local-42}"
    clean_env["PYTHONNOUSERSITE"] = "1"
    clean_env["PYTHONDONTWRITEBYTECODE"] = "1"
    clean_env["PYTHONSAFEPATH"] = "1"
    clean_env.pop("PYTEST_ADDOPTS", None)
    clean_env.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)

    if extra_env:
        for k, v in extra_env.items():
            # extra_env is privileged input: hold it to the SAME allowlist as
            # the host environment instead of only the secret-pattern filter.
            if k in _ALLOWED_ENV_VARS and not _STRIP_KEY_PATTERNS.search(k):
                clean_env[k] = str(v)

    return clean_env


@dataclass(frozen=True)
class TargetVerificationEvidence:
    target_id: str
    target_version: str
    manifest_hash: str
    passed: bool
    visible_passed: bool
    hidden_passed: bool
    visible_exit_code: int
    hidden_exit_code: int
    visible_output: str
    hidden_output: str
    duration_seconds: float
    timestamp: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuilderBreakerVerificationEvidence:
    target_id: str
    target_version: str
    manifest_hash: str
    builder_functional_passed: bool
    builder_hidden_passed: bool
    breaker_exploit_passed: bool
    builder_passed: bool
    breaker_passed: bool
    builder_output: str
    breaker_output: str
    duration_seconds: float
    timestamp: float
    server_crashed: bool = False
    availability_degraded: bool = False
    unauthorized_mutation: bool = False
    flag_captured: bool = False
    deployment_ready: bool = True
    deployment_repaired: bool = False
    deployment_status: str = "DEPLOY_SUCCESS"
    verification_status: str = "verified_fail"
    breaker_semantic_evidence: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrustedBreakerSemanticEvidence:
    """A verifier/runtime-owned postcondition, never Fighter wire data."""

    condition_checked: bool = False
    condition_passed: bool = False
    evidence_ids: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    verifier_error: str = ""


_TRUSTED_BREAKER_FINDINGS = frozenset(
    {
        "server_crashed",
        "availability_degraded",
        "unauthorized_mutation",
        "flag_captured",
    }
)


def _breaker_entrypoint(
    breaker_files: dict[str, bytes | str],
) -> tuple[str, str | None]:
    """Classify a Fighter executable without interpreting it as proof."""
    if not breaker_files:
        return "no_breaker_artifact", None
    for rel, command in (
        ("exploit.py", "python3 exploit.py"),
        ("exploit.sh", "bash exploit.sh"),
        ("exploit.js", "node exploit.js"),
    ):
        if rel not in breaker_files:
            continue
        payload = breaker_files[rel]
        try:
            raw = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return "malformed_breaker_artifact", None
        if not text.strip():
            return "malformed_breaker_artifact", None
        return "valid_breaker_artifact", command
    return "missing_exploit_entrypoint", None


def _semantic_record(
    *,
    artifact_status: str,
    execution_started: bool,
    execution_completed: bool,
    process_return_code: int | None,
    fighter_claim_present: bool,
    trusted: TrustedBreakerSemanticEvidence | None,
) -> dict[str, Any]:
    """Keep process telemetry distinct from a trusted semantic postcondition."""
    if trusted is None:
        trusted = TrustedBreakerSemanticEvidence()
    elif not isinstance(trusted, TrustedBreakerSemanticEvidence):
        trusted = TrustedBreakerSemanticEvidence(
            verifier_error="invalid trusted semantic evidence"
        )
    evidence_ids = tuple(str(item) for item in trusted.evidence_ids if str(item))
    findings = tuple(
        item for item in trusted.findings if item in _TRUSTED_BREAKER_FINDINGS
    )
    verifier_error = str(trusted.verifier_error or "")
    condition_checked = bool(trusted.condition_checked) and not bool(verifier_error)
    condition_passed = bool(
        artifact_status == "valid_breaker_artifact"
        and execution_started
        and execution_completed
        and condition_checked
        and trusted.condition_passed
        and evidence_ids
        and findings
    )
    return {
        "artifact_status": artifact_status,
        "execution_started": execution_started,
        "execution_completed": execution_completed,
        "process_return_code": process_return_code,
        "fighter_claim_present": fighter_claim_present,
        "trusted_condition_checked": condition_checked,
        "trusted_condition_passed": condition_passed,
        "verifier_error": verifier_error or None,
        "evidence_ids": list(evidence_ids),
        "findings": list(findings if condition_passed else ()),
    }


def _submission_text(files: dict[str, bytes | str]) -> dict[str, str]:
    return {
        str(path): data.decode("utf-8") if isinstance(data, bytes) else str(data)
        for path, data in files.items()
        if not _blocked_submission_path(path)
    }


def _run_breaker_evaluator(
    bundle: TargetBundle,
    builder_files: dict[str, bytes | str],
    breaker_files: dict[str, bytes | str],
    *,
    timeout_seconds: int = 10,
    builder_hidden_passed: bool = False,
    breaker_execution: BreakerExecution | None = None,
) -> TrustedBreakerSemanticEvidence | None:
    """Run target-owned breaker evaluator script if present in private fixtures."""
    # ``breaker_files`` remains in the call signature for compatibility with
    # existing verifier callers, but is intentionally never serialized here.
    entrypoint = bundle.verification.breaker_evaluator
    if not (bundle.private_fixture_files and entrypoint in bundle.private_fixture_files):
        return None

    request = {
        "schema_version": 1,
        "target_id": bundle.id,
        "manifest_hash": bundle.manifest_hash,
        "evaluator_hash": bundle.evaluator_hash,
        "builder_files": _submission_text({**bundle.starter_files, **builder_files}),
        # The Breaker already ran in a separate execution boundary. Never copy
        # its source into this private evaluator process: the evaluator Volume
        # is trusted-only, and read access to it would let a malicious artifact
        # recover hidden harness material. Evaluators consume only the bounded
        # execution observation below and their target-owned postconditions.
        "breaker_files": {},
        "breaker_execution": {
            "schema_version": 1,
            "started": bool(breaker_execution and breaker_execution.started),
            "completed": bool(breaker_execution and breaker_execution.completed),
            "return_code": (
                breaker_execution.return_code if breaker_execution is not None else None
            ),
            "stdout": breaker_execution.stdout if breaker_execution is not None else "",
            "stderr": breaker_execution.stderr if breaker_execution is not None else "",
        },
    }
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))

    try:
        with tempfile.TemporaryDirectory(prefix="arena-private-breaker-eval-") as temp:
            private_root = pathlib.Path(temp).resolve()
            for rel, data in bundle.private_fixture_files.items():
                safe = validate_safe_relative_path(rel, context="private breaker evaluator")
                dest = private_root / safe
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            env = _build_hardened_env(private_root)
            env["HOME"] = str(private_root)
            env["TMPDIR"] = str(private_root)
            env.pop("ARENA_FLAG", None)
            # -I excludes submission cwd, user site and ambient Python config.
            result = subprocess.run(
                [sys.executable, "-I", str(private_root / entrypoint)],
                input=encoded, cwd=private_root, env=env,
                text=True, capture_output=True, timeout=timeout_seconds,
            )
        if result.returncode != 0:
            return TrustedBreakerSemanticEvidence(verifier_error="breaker_evaluator_execution_failed")
        if len(result.stdout) > 32768:
            raise ValueError("oversized evaluator result")
        value = json.loads(result.stdout)
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "condition_checked", "condition_passed", "findings"}
            or type(value["schema_version"]) is not int
            or value["schema_version"] != 1
            or value["condition_checked"] is not True
            or type(value["condition_passed"]) is not bool
            or not isinstance(value["findings"], list)
            or not all(isinstance(x, str) and x in _TRUSTED_BREAKER_FINDINGS for x in value["findings"])
            or (value["condition_passed"] and not value["findings"])
            or (not value["condition_passed"] and value["findings"])
        ):
            raise ValueError("invalid evaluator result")
        evidence_id = "trusted:breaker:" + hashlib.sha256(encoded.encode()).hexdigest()
        return TrustedBreakerSemanticEvidence(
            condition_checked=True,
            condition_passed=value["condition_passed"],
            evidence_ids=(evidence_id,),
            findings=tuple(value["findings"]),
        )
    except subprocess.TimeoutExpired:
        return TrustedBreakerSemanticEvidence(verifier_error="breaker_evaluator_timeout")
    except (ValueError, UnicodeError, TypeError):
        return TrustedBreakerSemanticEvidence(verifier_error="breaker_evaluator_invalid_result")
    except OSError:
        return TrustedBreakerSemanticEvidence(verifier_error="breaker_evaluator_unavailable")


def verify_target_submission(
    bundle: TargetBundle,
    submitted_files: dict[str, bytes | str],
    *,
    run_visible: bool = True,
    run_hidden: bool = True,
    extra_env: dict[str, str] | None = None,
    timeout_seconds: int = 15,
    trusted_host: bool = False,
) -> TargetVerificationEvidence:
    """Execute verification against submitted artifacts in an isolated, sanitized workspace."""
    start_time = time.time()

    # Seatbelt: manifest-supplied verification commands must never execute in
    # the backend host process (which holds APPWRITE/HOST_*/FERNET secrets)
    # unless this call is the trusted /internal/verify path (trusted_host) or
    # an explicit local-test override.
    if (
        not trusted_host
        and os.environ.get("ARENA_IN_SANDBOX") != "1"
        and os.environ.get("ARENA_VERIFIER_ALLOW_INPROCESS") != "1"
    ):
        return TargetVerificationEvidence(
            target_id=bundle.id,
            target_version=bundle.version,
            manifest_hash=bundle.manifest_hash,
            passed=False,
            visible_passed=False,
            hidden_passed=False,
            visible_exit_code=126,
            hidden_exit_code=126,
            visible_output=(
                "Verifier refused: verification commands are not executed outside "
                "the sandbox (set ARENA_VERIFIER_ALLOW_INPROCESS=1 to override for local testing)"
            ),
            hidden_output="",
            duration_seconds=0.0,
            timestamp=time.time(),
            details={"blocked": "in-process execution refused"},
        )

    with tempfile.TemporaryDirectory(prefix=f"arena-verify-{bundle.id}-") as tmp_dir:
        work = pathlib.Path(tmp_dir).resolve()

        # 1. Materialize starter files
        for rel_path, data in bundle.starter_files.items():
            dest = (work / rel_path).resolve()
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

        # 2. Materialize fighter's submitted artifacts
        for rel_path, payload in submitted_files.items():
            if _blocked_submission_path(rel_path):
                continue
            clean_rel = str(rel_path).replace("\\", "/").strip()
            dest = (work / clean_rel).resolve()
            try:
                dest.relative_to(work)
            except ValueError:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            raw_bytes = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
            dest.write_bytes(raw_bytes)

        # 3. Mount visible tests
        if run_visible and bundle.visible_test_files:
            vis_root = work / "tests" / "visible"
            for rel_path, data in bundle.visible_test_files.items():
                dest = (vis_root / rel_path).resolve()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)

        # 4. Mount hidden tests (verifier workspace only)
        if run_hidden and bundle.hidden_test_files:
            hid_root = work / "tests" / "hidden"
            for rel_path, data in bundle.hidden_test_files.items():
                dest = (hid_root / rel_path).resolve()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)

        # 5. Mount extra trusted fixtures (breaker harness, etc.). Never fighter-visible.
        for rel_path, data in (bundle.private_fixture_files or {}).items():
            clean_rel = str(rel_path).replace("\\", "/").strip()
            if not clean_rel or ".." in clean_rel.split("/"):
                continue
            dest = (work / clean_rel).resolve()
            try:
                dest.relative_to(work)
            except ValueError:
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)

        # Make shell scripts executable if any
        for script in work.rglob("*.sh"):
            script.chmod(0o755)

        ini_path = _write_arena_pytest_harness(work)
        env = _build_hardened_env(work, extra_env)

        vis_exit = 0
        vis_out = ""
        vis_passed = True

        if run_visible and bundle.verification.visible_command:
            vis_cmd = _harden_pytest_command(
                bundle.verification.visible_command, ini_path=ini_path, root=work
            )
            block_reason = command_block_reason(vis_cmd, allow_network=bundle.network)
            if block_reason:
                vis_exit = 126
                vis_out = f"Visible verification command blocked: {block_reason}"
                vis_passed = False
            else:
                try:
                    r_vis = subprocess.run(
                        vis_cmd,
                        cwd=work,
                        shell=True,
                        text=True,
                        capture_output=True,
                        timeout=timeout_seconds,
                        env=env,
                    )
                    vis_exit = r_vis.returncode
                    vis_out = (r_vis.stdout or "") + (r_vis.stderr or "")
                    vis_passed = (vis_exit == 0)
                except subprocess.TimeoutExpired:
                    vis_exit = 124
                    vis_out = f"Visible verification timed out after {timeout_seconds}s"
                    vis_passed = False
                except Exception as exc:
                    vis_exit = 1
                    vis_out = f"Visible verification failed to execute: {exc}"
                    vis_passed = False

        hid_exit = 0
        hid_out = ""
        hid_passed = True

        if run_hidden and bundle.verification.hidden_command:
            hid_cmd = _harden_pytest_command(
                bundle.verification.hidden_command, ini_path=ini_path, root=work
            )
            block_reason = command_block_reason(hid_cmd, allow_network=bundle.network)
            if block_reason:
                hid_exit = 126
                hid_out = f"Hidden verification command blocked: {block_reason}"
                hid_passed = False
            else:
                try:
                    r_hid = subprocess.run(
                        hid_cmd,
                        cwd=work,
                        shell=True,
                        text=True,
                        capture_output=True,
                        timeout=timeout_seconds,
                        env=env,
                    )
                    hid_exit = r_hid.returncode
                    hid_out = (r_hid.stdout or "") + (r_hid.stderr or "")
                    hid_passed = (hid_exit == 0)
                except subprocess.TimeoutExpired:
                    hid_exit = 124
                    hid_out = f"Hidden verification timed out after {timeout_seconds}s"
                    hid_passed = False
                except Exception as exc:
                    hid_exit = 1
                    hid_out = f"Hidden verification failed to execute: {exc}"
                    hid_passed = False

    duration = time.time() - start_time
    overall_passed = vis_passed and (hid_passed if run_hidden else True)

    return TargetVerificationEvidence(
        target_id=bundle.id,
        target_version=bundle.version,
        manifest_hash=bundle.manifest_hash,
        passed=overall_passed,
        visible_passed=vis_passed,
        hidden_passed=hid_passed,
        visible_exit_code=vis_exit,
        hidden_exit_code=hid_exit,
        visible_output=vis_out[:8000],
        hidden_output=hid_out[:8000],
        duration_seconds=round(duration, 3),
        timestamp=time.time(),
        details={
            "visible_command": bundle.verification.visible_command,
            "hidden_command": bundle.verification.hidden_command,
            "ranked_requires_hidden_pass": bundle.verification.ranked_requires_hidden_pass,
        },
    )


def verify_builder_breaker_submission(
    bundle: TargetBundle,
    builder_files: dict[str, bytes | str],
    breaker_files: dict[str, bytes | str],
    *,
    extra_env: dict[str, str] | None = None,
    timeout_seconds: int = 20,
    trusted_host: bool = False,
    trusted_semantic_evidence: TrustedBreakerSemanticEvidence | None = None,
) -> BuilderBreakerVerificationEvidence:
    """Asymmetrically evaluate a Builder vs Breaker match.

    1. Builder evaluation: tests functional correctness + hidden security rules on builder output.
    2. Breaker evaluation: runs breaker exploit against builder output to see if exploit succeeded.
    """
    start_time = time.time()

    # Step 1: Evaluate Builder
    builder_ev = verify_target_submission(
        bundle,
        builder_files,
        run_visible=True,
        run_hidden=True,
        extra_env=extra_env,
        timeout_seconds=timeout_seconds,
        trusted_host=trusted_host,
    )

    # Step 2: Evaluate Breaker against Builder output
    artifact_status, breaker_cmd = _breaker_entrypoint(breaker_files)
    breaker_out = ""
    execution_started = False
    execution_completed = False
    process_return_code: int | None = None

    breaker_execution: BreakerExecution | None = None

    # This execution is Fighter telemetry only. It happens in a separate Modal
    # Sandbox in production, which has no evaluator Volume attached. A return
    # code or output marker is never trusted semantic evidence.
    if builder_ev.details.get("blocked"):
        trusted_semantic_evidence = TrustedBreakerSemanticEvidence(
            verifier_error="verifier_execution_refused"
        )
    elif breaker_cmd:
        block_reason = command_block_reason(
            breaker_cmd, allow_network=bundle.network
        )
        if block_reason:
            breaker_out = f"Breaker command blocked: {block_reason}"
        else:
            execution_files = {
                **bundle.starter_files,
                **builder_files,
                **breaker_files,
            }
            breaker_execution = run_breaker_isolated(
                breaker_cmd,
                execution_files,
                timeout_seconds=timeout_seconds,
                allow_network=bundle.network,
                runtime=bundle.runtime,
            )
            breaker_out = (
                (breaker_execution.stdout or "")
                + (breaker_execution.stderr or "")
            )
            execution_started = breaker_execution.started
            execution_completed = breaker_execution.completed
            process_return_code = breaker_execution.return_code
            if breaker_execution.error:
                trusted_semantic_evidence = TrustedBreakerSemanticEvidence(
                    verifier_error=breaker_execution.error
                )

    if (
        trusted_semantic_evidence is None
        and execution_completed
        and process_return_code == 0
    ):
        trusted_semantic_evidence = _run_breaker_evaluator(
            bundle,
            builder_files,
            breaker_files,
            timeout_seconds=timeout_seconds,
            builder_hidden_passed=builder_ev.hidden_passed,
            breaker_execution=breaker_execution,
        )

    duration = time.time() - start_time

    # Builder passes if functional & hidden tests pass AND breaker was unable to exploit
    # Breaker passes if breaker successfully exploited
    builder_functional = builder_ev.visible_passed
    builder_hidden = builder_ev.hidden_passed

    semantic = _semantic_record(
        artifact_status=artifact_status,
        execution_started=execution_started,
        execution_completed=execution_completed,
        process_return_code=process_return_code,
        fighter_claim_present=bool(breaker_out.strip()),
        trusted=trusted_semantic_evidence,
    )
    breaker_exploit_passed = bool(semantic["trusted_condition_passed"])
    findings = set(semantic["findings"])
    verifier_error = str(semantic.get("verifier_error") or "")

    builder_passed = (
        builder_functional
        and builder_hidden
        and not breaker_exploit_passed
        and not verifier_error
    )
    breaker_passed = breaker_exploit_passed and not verifier_error

    return BuilderBreakerVerificationEvidence(
        target_id=bundle.id,
        target_version=bundle.version,
        manifest_hash=bundle.manifest_hash,
        builder_functional_passed=builder_functional,
        builder_hidden_passed=builder_hidden,
        breaker_exploit_passed=breaker_exploit_passed,
        builder_passed=builder_passed,
        breaker_passed=breaker_passed,
        builder_output=f"Visible: {builder_ev.visible_output}\nHidden: {builder_ev.hidden_output}"[:8000],
        breaker_output=breaker_out[:8000],
        duration_seconds=round(duration, 3),
        timestamp=time.time(),
        server_crashed="server_crashed" in findings,
        availability_degraded="availability_degraded" in findings,
        unauthorized_mutation="unauthorized_mutation" in findings,
        flag_captured="flag_captured" in findings,
        deployment_ready=builder_functional,
        deployment_repaired=False,
        deployment_status="DEPLOY_SUCCESS" if builder_functional else "DEPLOY_FAILED",
        verification_status="infra_failure" if verifier_error else (
            "verified_pass" if builder_passed else "verified_fail"
        ),
        breaker_semantic_evidence=semantic,
        details={
            "builder_evidence": builder_ev.details,
            "breaker_command": breaker_cmd,
            "breaker_execution_error": (
                breaker_execution.error if breaker_execution is not None else ""
            ),
        },
    )
