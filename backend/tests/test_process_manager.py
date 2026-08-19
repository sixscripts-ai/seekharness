import time

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
