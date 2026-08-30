from __future__ import annotations
import os, pathlib, shutil, subprocess, tempfile, yaml, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]


def overlay(src, dst):
    if not src.exists():
        return
    if src.is_symlink():
        raise ValueError(f"evaluator overlay source is a symlink: {src}")
    for p in src.rglob("*"):
        if p.is_symlink():
            raise ValueError(f"symlink rejected in evaluator overlay: {p}")
        if p.is_file():
            o = dst / p.relative_to(src)
            o.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, o, follow_symlinks=False)


def evaluator_package(name):
    env = os.environ.get("ARENA_EVALUATOR_DIR")
    if env:
        candidate = pathlib.Path(env) / name
        if candidate.is_dir() and not candidate.is_symlink():
            return candidate
        return None
    repo = ROOT.parent / "evaluators" / name
    if repo.is_dir() and not repo.is_symlink():
        return repo
    return None


def run(cmd, cwd, extra=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(cwd) + os.pathsep + env.get("PYTHONPATH", "")
    env.update(extra or {})
    return subprocess.run(cmd, cwd=cwd, shell=True, text=True, capture_output=True, timeout=15, env=env)


def main(name):
    td = (ROOT / "targets" / name) if (ROOT / "targets" / name).exists() else (ROOT / name)
    d = yaml.safe_load((td / "target.yaml").read_text())
    ws = d["workspace"]
    ver = d["verification"]
    ev = evaluator_package(name)
    if ev is None:
        print(f"{name}: private evaluator package missing", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="arena-target-") as x:
        w = pathlib.Path(x)
        shutil.copytree(td / ws["starter_dir"], w, dirs_exist_ok=True)
        overlay(td / ws["visible_tests_dir"], w / "tests/visible")
        starter = run(ver["visible_command"], w)
        try:
            overlay(ev / "reference", w)
            overlay(ev / "tests" / "hidden", w / "tests/hidden")
        except ValueError as exc:
            print(f"{name}: {exc}", file=sys.stderr)
            return 1
        vis = run(ver["visible_command"], w, {"ARENA_FLAG": "FLAG{tinyshop-local-42}"})
        hid = run(ver["hidden_command"], w, {"ARENA_FLAG": "FLAG{tinyshop-local-42}"})
        if vis.returncode or hid.returncode:
            print(vis.stdout, vis.stderr, hid.stdout, hid.stderr, sep="\n", file=sys.stderr)
            return 1
        print(f"{name}: starter={'PASS' if starter.returncode==0 else 'FAIL'}; reference=PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
