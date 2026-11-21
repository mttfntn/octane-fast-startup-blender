"""Integration test in a real (headless) Blender, with the stub Octane add-on.

Usage:  python tests/blender_test.py [path/to/blender]
        (default: $BLENDER, else "blender" on PATH)

Every configuration gets its own throwaway user profile (BLENDER_USER_RESOURCES
in a temp folder), so your own Blender settings and add-ons are never used:
  no_fix            stub Octane only                -> slow, not patched (proves the test can fail)
  startup_copy      script copied to scripts/startup -> patched, fast
  script_directory  repo added to Preferences > File Paths > Script Directories
                                                     -> patched, fast (the documented install)
  online            like startup_copy, with something listening on port 50051
                                                     -> patched, every call passes through
The stub makes each Octane server request wait OCTANE_STUB_DELAY (1 s) when
no server listens, like the real add-on, so a New File without the fix costs ~3 s.
"""
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SCRIPT = os.path.join(REPO, "startup", "octane_fast_start.py")
BLENDER = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BLENDER")) or shutil.which("blender")

SETUP = r'''
import bpy, addon_utils, sys
addon_utils.enable("octane", default_set=True)
repo = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else ""
if repo:
    d = bpy.context.preferences.filepaths.script_directories.new()
    d.directory = repo
bpy.ops.wm.save_userpref()
'''

PROBE = r'''
import bpy, sys, time
from octane.core import client
fs = sys.modules.get("octane_fast_start")
print("RES octane_enabled", "octane" in bpy.context.preferences.addons)
print("RES patched", getattr(client.OctaneBlender, "_fast_start_patched", False))
print("RES fast_start_file", getattr(fs, "__file__", None))
t = time.perf_counter(); bpy.ops.wm.read_homefile(); dt = time.perf_counter() - t
print("RES new_file_seconds %.3f" % dt)
print("RES calls_reaching_octane", len(client.CALLS))
print("RES skipped", fs._state["skipped"] if fs else None)
'''


def blender(args, env):
    return subprocess.run([BLENDER, "-b", "--python-exit-code", "1"] + args, env=env,
                          capture_output=True, text=True, errors="replace", timeout=300)


def listener():
    s = socket.socket()
    s.bind(("127.0.0.1", 50051))
    s.listen(16)

    def accept():
        while True:
            try:
                s.accept()[0].close()
            except OSError:
                return
    threading.Thread(target=accept, daemon=True).start()
    return s


def run_config(name, tmp):
    res = os.path.join(tmp, name)
    addons = os.path.join(res, "scripts", "addons")
    shutil.copytree(os.path.join(HERE, "stub_octane", "octane"), os.path.join(addons, "octane"))
    if name in ("startup_copy", "online"):
        os.makedirs(os.path.join(res, "scripts", "startup"))
        shutil.copy(SCRIPT, os.path.join(res, "scripts", "startup"))
    env = dict(os.environ, BLENDER_USER_RESOURCES=res, OCTANE_STUB_DELAY="1.0")
    for var in ("BLENDER_USER_SCRIPTS", "BLENDER_USER_CONFIG", "BLENDER_USER_EXTENSIONS"):
        env.pop(var, None)

    setup_file = os.path.join(tmp, "setup.py")
    probe_file = os.path.join(tmp, "probe.py")
    with open(setup_file, "w") as f:
        f.write(SETUP)
    with open(probe_file, "w") as f:
        f.write(PROBE)
    extra = ["--", REPO] if name == "script_directory" else []
    p = blender(["--factory-startup", "--python", setup_file] + extra, env)
    if p.returncode != 0:
        raise SystemExit(f"[{name}] setup failed:\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")

    srv = listener() if name == "online" else None
    try:
        t = time.perf_counter()
        p = blender(["--python", probe_file], env)
        total = time.perf_counter() - t
    finally:
        if srv:
            srv.close()
    if p.returncode != 0:
        raise SystemExit(f"[{name}] probe failed:\n{p.stdout[-2000:]}\n{p.stderr[-2000:]}")
    out = {}
    for line in p.stdout.splitlines():
        if line.startswith("RES "):
            key, _, value = line[4:].partition(" ")
            out[key] = value
    out["startup_total_seconds"] = "%.2f" % total
    return out


def main():
    if not BLENDER:
        raise SystemExit("Blender not found: pass its path or set $BLENDER")
    expect = {
        "no_fix": lambda r: r["patched"] == "False" and float(r["new_file_seconds"]) > 2.0,
        "startup_copy": lambda r: r["patched"] == "True" and float(r["new_file_seconds"]) < 0.5
        and r["calls_reaching_octane"] == "0",
        "script_directory": lambda r: r["patched"] == "True" and float(r["new_file_seconds"]) < 0.5
        and os.path.normcase(os.path.realpath(r["fast_start_file"])) == os.path.normcase(os.path.realpath(SCRIPT)),
        "online": lambda r: r["patched"] == "True" and r["skipped"] == "0"
        # API_START + 3 calls for the startup file Blender loads + 3 for the New File
        and int(r["calls_reaching_octane"]) == 7,
    }
    failed = []
    tmp = tempfile.mkdtemp(prefix="octane_fast_start_test_")
    try:
        for name, check in expect.items():
            r = run_config(name, tmp)
            ok = check(r)
            failed += [] if ok else [name]
            print(f"{name:17} {'PASS' if ok else 'FAIL'}  " + "  ".join(f"{k}={v}" for k, v in r.items()))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nRESULT:", "all passed" if not failed else "FAILED: " + ", ".join(failed))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
