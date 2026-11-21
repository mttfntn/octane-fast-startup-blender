# Octane Fast Start

Makes Blender start in ~2–3 s instead of ~20 s, and open/new files in ~0.01 s
instead of ~8 s, **while keeping the Octane add-on enabled**.

| | Without | With |
|---|---|---|
| Blender startup | ~18–22 s | ~2.7 s |
| File > New / Open | ~8 s | ~0.01 s |
| Octane enabled | yes | yes |

Measured 2026-11-18 on Blender 5.3.0 + Octane add-on client (OctaneServer Prime 31.12).

Version history:
- 2026-11-18: built and tested with OctaneBlender add-on **31.7.0**.
- 2026-11-18: upgraded to OctaneBlender add-on **32.2.0 alpha** — fix worked
  unchanged (`check.py`: OK, startup 2.9 s, New File 0.01 s).
  Old add-on backed up to `%APPDATA%\Blender Foundation\Blender\5.3\octane_backup_31.7.0`.
  To roll back: close Blender, delete `scripts\addons\octane`, move the backup
  folder back to `scripts\addons\octane`.

---

## 1. The problem (how it was found)

1. **Compared startup times** (headless, `blender -b`):
   factory settings = 1.0 s, user settings = 18–22 s → something in the user setup.
2. **Timed each add-on** by enabling them one by one in a factory-startup Blender:
   Octane = 4.9 s, all others together < 1 s.
3. **Disabled only Octane** (in a *copy* of the config, via `BLENDER_USER_CONFIG`):
   startup dropped to 1.9 s → Octane is ~95 % of the lag.
4. **Profiled Octane** with `cProfile` while enabling it and loading a file.
   The Python code is fast; all the time is in three native calls into
   `octane_blender.pyd`, each waiting ~4 s:

   | When | Call | Time |
   |---|---|---|
   | Add-on load (startup) | `OctaneBlender.utils_function(API_START)` | ~4 s |
   | **Every** file load | `OctaneBlender.reset_render()` (via `reset_resource_cache`) | ~4–5 s |
   | **Every** file load | `utils_function(UPDATE_OCIO_SETTINGS)` (via `ocio.update_ocio_info`) | ~3–4 s |

5. **Root cause:** the Octane add-on is a *client* that talks over gRPC to the
   **Octane Server** at `localhost:50051`. When the server is not running, every
   request waits for a connection timeout (~4 s) before failing. Octane already
   handles the failure correctly — it just takes 4 s to find out.

## 2. How the fix works

`octane_fast_start.py` is a Blender **startup script** (it lives in
`scripts/startup/`, which Blender loads *before* add-ons).

1. It installs an **import hook** (`sys.meta_path` finder). The moment Octane
   imports its module `octane.core.client`, the hook wraps three methods of the
   `OctaneBlender` class:
   `utils_function`, `reset_render`, `update_server_settings`.
2. Each wrapper first asks: **is anything listening on the server port?**
   (`socket.create_connection(("127.0.0.1", 50051), timeout=0.05)` — instant
   when the server runs, ≤50 ms when it doesn't).
   - Server **offline** → skip the call and return what a failed call returns
     (`""` or `None`). Takes ~0 s instead of ~4 s.
   - Server **online** → call the original method, unchanged.
3. A **background thread** re-checks the port every 2 s, so the check never
   blocks the UI.
4. A **Blender timer** watches for the server coming online (2 checks in a row,
   so it doesn't hit a server that is still starting). Then it runs the work that
   was skipped: `API_START`, `ocio.update_ocio_info()`,
   `resource_cache.reset_resource_cache()`.

Nothing inside the Octane add-on folder is changed, so **Octane updates don't
overwrite the fix**, and your scenes/settings are never touched.

## 3. Files

| File | Purpose |
|---|---|
| `octane_fast_start.py` | The fix (startup script) |
| `check.py` | One-command test: is the fix active, how fast is New File, do the Octane methods still exist |
| `README.md` | This file |

## 4. Install / uninstall

Install: copy `octane_fast_start.py` to
```
%APPDATA%\Blender Foundation\Blender\5.3\scripts\startup\
```
then restart Blender. The system console shows `[Octane Fast Start] active ...`.

For a **new Blender version** (e.g. 5.4) copy it into that version's
`...\Blender\5.4\scripts\startup\` folder too.

Uninstall: delete that file and restart Blender.

## 5. After an Octane update — what to do

1. Restart Blender, then run:
   ```
   python check.py
   ```
   (pass the blender.exe path as an argument if Blender moved).
2. `RESULT: OK` → nothing to do.
3. `NOT WORKING` → look at which line failed:
   - `patched False` or `octane_import_error` → Octane renamed/moved the module
     `octane/core/client.py` or the class `OctaneBlender`. Update `TARGET` and
     the class name in `octane_fast_start.py`.
   - `method ... MISSING` → a wrapped method was renamed. Find the new name in
     `octane/core/client.py`.
   - `new_file_seconds` still ~8 s → Octane added a **new** slow server call.
     Profile it again (see the prompt below) and wrap that method too.
4. If an update breaks something, delete the startup file — Blender is then
   exactly as before (just slow again).

The Octane add-on lives at
`...\Blender\5.3\scripts\addons\octane\` (key files: `core/client.py`,
`utils/ocio.py`, `core/resource_cache.py`, `handlers.py`).

## 6. Reusable prompt (for Claude, next time Octane updates)

Copy everything in the box into a new Claude Code session opened in this folder:

```text
I use Blender with the Octane add-on (client that talks to Octane Server over
gRPC on localhost:50051). I have a startup script "Octane Fast Start"
(octane_fast_start/octane_fast_start.py, installed in
%APPDATA%\Blender Foundation\Blender\<version>\scripts\startup\) that makes
Blender start fast when Octane Server is NOT running. It uses a sys.meta_path
import hook to wrap OctaneBlender.utils_function / reset_render /
update_server_settings in octane.core.client: if the server port is not
listening (50 ms socket probe, refreshed by a background thread) the call is
skipped; when the server comes online a timer runs API_START,
ocio.update_ocio_info() and resource_cache.reset_resource_cache().
Read octane_fast_start/README.md for the full background.

Octane just published an update. Please:
1. Run `python octane_fast_start/check.py` and tell me the result.
2. If it is not OK, read the new Octane add-on code in
   %APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\octane\
   (core/client.py, utils/ocio.py, core/resource_cache.py, handlers.py) and find
   what changed (renamed module/class/methods, new server calls).
3. Profile Octane headlessly with cProfile (enable the add-on + bpy.ops.wm.read_homefile())
   in a separate `blender -b` process using a COPY of my config
   (BLENDER_USER_CONFIG pointing to a temp copy of userpref.blend/startup.blend).
   Never run tests inside my open Blender session.
4. Update octane_fast_start.py so the slow server calls are skipped again
   when the server is offline, and still go through unchanged when it is online.
5. Test in the config copy: startup time, New File time, and the
   "server comes online" path (fake listener on the port, stubbed Octane calls).
6. Install the updated file into scripts/startup, run check.py again,
   and update README.md (measurements, date, versions).
Do not modify the Octane add-on's own files.
```

## 7. Optional alternative

If you **always** start OctaneServer (`C:\Program Files\OctaneServerPrime31.12\OctaneServer.exe`)
before Blender, the fix simply passes every call through to Octane unchanged.
(Not yet measured: how fast Octane's calls are when the real server is running.
The "server comes online" path was tested with a stand-in listener, not the
real OctaneServer — do one Octane render to confirm.)
