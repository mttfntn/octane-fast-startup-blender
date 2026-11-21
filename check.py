# SPDX-License-Identifier: GPL-3.0-or-later
"""Check whether Octane Fast Start is working after an Octane (or Blender) update.

Runs a separate headless Blender with your normal settings (your open Blender
is not touched; set BLENDER_USER_RESOURCES to a folder to use a scratch
profile instead) with the REAL Octane add-on, and reports:
  * whether the fix is active
  * how long a New File takes (should be ~0.01 s with the fix, ~8 s without)
  * whether the Octane methods the fix relies on still exist

Usage:
    python check.py
    python check.py "C:/Program Files/Blender Foundation/Blender 5.3/blender.exe"
"""
import os
import subprocess
import sys
import tempfile
import time

BLENDER = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"

PROBE = r'''
import bpy, sys, time, inspect
print("CHK octane_enabled", "octane" in bpy.context.preferences.addons)
fs = sys.modules.get("octane_fast_start")
print("CHK fast_start_loaded", fs is not None)
try:
    from octane.core.client import OctaneBlender as C
    print("CHK patched", getattr(C, "_fast_start_patched", False))
    for name in ("utils_function", "reset_render", "update_server_settings"):
        fn = getattr(C, name, None)
        print("CHK method", name, "exists" if fn else "MISSING")
    from octane.utils import consts
    print("CHK API_START", hasattr(consts.UtilsFunctionType, "API_START"))
except Exception as e:
    print("CHK octane_import_error", e)
if fs:
    print("CHK server_online", fs._state["up"], "skipped_calls", fs._state["skipped"])
t = time.perf_counter(); bpy.ops.wm.read_homefile(); print("CHK new_file_seconds %.2f" % (time.perf_counter() - t))
'''

with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
    f.write(PROBE)
    probe_path = f.name
try:
    t = time.perf_counter()
    p = subprocess.run([BLENDER, "-b", "--python", probe_path], capture_output=True, text=True, errors="replace")
    total = time.perf_counter() - t
finally:
    os.unlink(probe_path)

lines = [l[4:] for l in p.stdout.splitlines() if l.startswith("CHK ")]
print("\n".join(lines))
print(f"startup_total_seconds {total:.2f}")
ok = any(l == "patched True" for l in lines) and any(
    l.startswith("new_file_seconds") and float(l.split()[-1]) < 1.0 for l in lines)
print("\nRESULT:", "OK - fast start is working" if ok else
      "NOT WORKING - see README.md section 'After an Octane update'")
