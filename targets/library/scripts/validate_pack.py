from __future__ import annotations
import pathlib, subprocess, sys, yaml
ROOT=pathlib.Path(__file__).resolve().parents[1]
req={"schema_version","id","name","category","difficulty","format","runtime","description","workspace","network","verification","limits","safety"}
manifests = sorted((ROOT / 'targets').glob('*/target.yaml'))
if not manifests:
    manifests = sorted(ROOT.glob('*/target.yaml'))

fail = []
for mp in manifests:
    d = yaml.safe_load(mp.read_text())
    missing = req - set(d)
    if missing or d.get('id') != mp.parent.name:
        fail.append(mp.parent.name)
        print(f"{mp.parent.name}: manifest invalid {sorted(missing)}")
        continue
    r = subprocess.run(
        [sys.executable, str(ROOT / 'scripts' / 'validate_target.py'), mp.parent.name],
        text=True,
        capture_output=True,
        timeout=45,
    )
    print((r.stdout or r.stderr).strip(), flush=True)
    if r.returncode:
        fail.append(mp.parent.name)
if fail:
    print('FAILED:',', '.join(fail)); raise SystemExit(1)
print('All 10 targets validated.')
