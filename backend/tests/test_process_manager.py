import time
import os

from agent_arena.sandbox.executors.procs import ProcessManager


def test_process_manager_bg_kill_logs(tmp_path):
    mgr = ProcessManager(tmp_path)
    try:
        mp = mgr.start("echoer", "echo hello-from-bg; sleep 30")
        assert mp.alive()
        deadline = time.time() + 2
        logs = ""
        while time.time() < deadline:
            logs = mgr.logs("echoer")
            if "hello-from-bg" in logs:
                break
            time.sleep(0.05)
        assert "hello-from-bg" in logs
        listed = mgr.list()
        assert "echoer" in listed
        killed = mgr.kill("echoer")
        assert "KILLED" in killed
        assert not mp.alive()
        assert "ERROR" in mgr.kill("missing")
        assert "ERROR" in mgr.logs("missing")
    finally:
        mgr.killall()


def test_process_manager_uses_the_explicit_scrubbed_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATABASE_URL", "postgresql://control-plane/arena")
    mgr = ProcessManager(tmp_path)
    try:
        mp = mgr.start(
            "env-probe",
            'printf "%s|%s\\n" "$ONLY_VALUE" "${DATABASE_URL-absent}"',
            env={"PATH": os.environ.get("PATH", ""), "ONLY_VALUE": "present"},
        )
        deadline = time.time() + 2
        logs = ""
        while time.time() < deadline:
            logs = mgr.logs("env-probe")
            if "present|absent" in logs or not mp.alive():
                break
            time.sleep(0.05)
        assert "present|absent" in logs
        assert "control-plane" not in logs
    finally:
        mgr.killall()
