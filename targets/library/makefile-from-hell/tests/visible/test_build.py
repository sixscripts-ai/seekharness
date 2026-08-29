import pathlib, subprocess, shutil
ROOT=pathlib.Path(__file__).resolve().parents[2]

def run(*args):
    return subprocess.run(args,cwd=ROOT,text=True,capture_output=True,check=True)

def test_build_and_output():
    run("make","clean")
    run("make")
    exe=ROOT/"build"/"calc"
    assert exe.exists()
    p=run(str(exe),"7","5")
    assert p.stdout.strip()=="sum=12 product=35"
