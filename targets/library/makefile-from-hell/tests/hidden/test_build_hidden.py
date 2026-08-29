import pathlib, subprocess, time
ROOT=pathlib.Path(__file__).resolve().parents[2]

def run(*args):
    return subprocess.run(args,cwd=ROOT,text=True,capture_output=True,check=True)

def test_make_test_target():
    run("make","clean"); run("make"); p=run("make","test")
    assert "TEST_PASS" in p.stdout

def test_header_change_rebuilds_math_object():
    run("make","clean"); run("make")
    obj=ROOT/"build"/"mathx.o"
    before=obj.stat().st_mtime_ns
    time.sleep(1.05)
    hdr=ROOT/"include"/"mathx.h"
    hdr.write_text(hdr.read_text()+"\n/* touch */\n")
    run("make")
    assert obj.stat().st_mtime_ns > before
