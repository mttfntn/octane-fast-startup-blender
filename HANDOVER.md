# Handover: Octane Fast Start

Everything a new maintainer needs. For a short version aimed at AI coding
assistants, see [AGENTS.md](AGENTS.md).

## 1. What the project is

A single Blender **startup script** (`startup/octane_fast_start.py`) that removes
the startup and file-load delays the OctaneRender for Blender add-on (by OTOY)
causes while no Octane Server is running. It does not modify Octane: it wraps
three methods of Octane's client class at runtime, and deleting the script undoes
everything. It is unofficial and contains no OTOY code.

Why it exists: the Octane add-on is a gRPC client of the Octane Server
(`localhost:50051` by default). With no server running, each request waits for a
connection timeout. Add-on 31.7 made three such requests (~4 s each): one at
startup and two on every File > New / Open. Add-on 32.2 has its own 200 ms probe
but still pays ~0.8 s per file load. See the README for measurements.

## 2. What you need

| Need | Version / note |
|---|---|
| Blender | **5.3** (the only supported version; CI tests exactly 5.3.0) |
| Octane add-on | tested with 31.7.0 and 32.2.0 alpha (only needed for `check.py`) |
| Python | any 3.10+ to run the tests and tools (Blender 5.3 bundles 3.13) |
| git, GitHub CLI (`gh`) | for releases |

Nothing needs installing with pip: the script and tests use only the standard library.

## 3. How the code is organised

| Path | What it is |
|---|---|
| `startup/octane_fast_start.py` | The script. The folder name `startup/` matters: Blender loads `<script dir>/startup/*.py` at launch, so the repo (or the release folder) can be added as a Script Directory. |
| `check.py` | Real-world check against the **real** Octane add-on, in a separate headless Blender. Run after every Octane or Blender update. |
| `tests/stub_octane/octane/` | A stand-in for the Octane add-on, with the same module and class names and simulated server timeouts. Used by all automated tests, so CI needs no Octane licence. |
| `tests/scenarios.py` | 8 behaviour scenarios (offline, online, offline→online, online→offline, custom port, `localhost`, reload, double register), each run in a fresh process with a fake `bpy`. Prints a JSON trace. |
| `tests/test_fast_start.py` | unittest assertions over those scenarios. |
| `tests/compare.py` | Runs every scenario on an old and a new version of the script and diffs the traces (behaviour-change detector). |
| `tests/blender_test.py` | Headless Blender with throwaway profiles: no fix / startup copy / repo as Script Directory / server online. |
| `tools/build.py` | Builds `dist/octane-fast-start-<version>.zip`. |
| `.github/workflows/tests.yml` | CI: unit tests (Linux and Windows) and the Blender test (Linux, Blender 5.3.0). |
| `.github/workflows/release.yml` | Tag `vX.Y.Z` → tests → build → GitHub release. |
| `HANDOVER.md`, `AGENTS.md` | Documentation (not shipped in the zip). |

## 4. How the main feature works

```
Blender start
 ├─ loads scripts/startup/*.py ──► octane_fast_start.register()
 │                                   └─ puts _Finder at the front of sys.meta_path
 └─ loads add-ons ──► "octane" package imports octane.core.client
                        └─ _Finder wraps the module loader; after the module runs, patch(module):
                             ├─ wraps OctaneBlender.utils_function / reset_render / update_server_settings
                             ├─ starts the _watch() thread (probe the port every 2 s)
                             └─ registers _timer() (Blender timer, every 2 s, main thread)
```

- **Wrapped call:** `_server_up()` returns the last probe result (it probes once
  if none exists yet). If the server is down, the call is counted in
  `_state["skipped"]` and returns `""` (for `utils_function`) or `None`, which is
  what Octane's own methods return on failure. A skipped `API_START` sets
  `pending_start`.
- **Server address:** read from Octane's add-on preferences
  (`octane_server_address`, `octane_addon_server_port`). Those preferences do
  **not** exist yet when `patch()` runs, because Octane imports its client before its
  `register()`. So the read is retried on the main thread (first wrapped call, or a
  timer tick) until it succeeds. `localhost` is probed as `127.0.0.1`.
- **Server comes online:** `_watch()` keeps a `streak` of successful probes;
  `_timer()` waits for `streak >= 2` and then calls `_on_server_online()`, which
  sends `API_START` (if it was skipped), `ocio.update_ocio_info()` and
  `resource_cache.reset_resource_cache()`, once per offline→online transition.
- **Server online:** every wrapped call goes straight to Octane's original method.

## 5. How to make a change

1. Edit `startup/octane_fast_start.py`. Keep it standard-library only.
2. Run the unit tests (section 6). Add a scenario to `tests/scenarios.py` and an
   assertion to `tests/test_fast_start.py` for new behaviour.
3. Check that nothing else changed in behaviour:
   ```powershell
   python tests/compare.py --git HEAD
   ```
   Every scenario must say `same`, unless the difference is intended. If it is,
   add it to `EXPECTED` in `compare.py` with the reason.
4. Run the Blender test and, if you have Octane, `check.py` in a scratch profile
   (section 6). Never test inside your open Blender or your real profile.
5. Small commits; push; check the Actions run.

**Docstrings vs comments:** the script has no Blender operators or panels, so
docstrings are never shown to users and are used freely. If you ever add an
operator, use `#` comments on the class, because Blender shows the class
docstring as the tooltip.

## 6. How to run the tests

```powershell
python -m unittest discover -s tests -v
```

```powershell
python tests/compare.py --git HEAD
```

```powershell
python tests/blender_test.py "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
```

With the real Octane add-on, without touching your own profile: make a scratch
folder `S` with `S\scripts\addons\octane` (a copy of the add-on),
`S\scripts\startup\octane_fast_start.py` and a `S\config\userpref.blend` with
Octane enabled. Then:

```powershell
$env:BLENDER_USER_RESOURCES = "C:\path\to\S"; python check.py
```

Expected: unit tests 8/8 OK; `compare.py` all `same` except
`custom_port_online` (the v1.0.0 bug fix, see section 9); Blender test
`all passed`; `check.py` `RESULT: OK`.

## 7. How to make a release

1. Set `__version__` in `startup/octane_fast_start.py` (e.g. `1.0.1`).
2. The release, license and language badges in `README.md` update themselves. Update the Blender badge only if the supported Blender version changed.
3. Update the measurements and tested versions in `README.md` if they changed.
4. Commit, then create an **annotated** tag. Its message becomes the release notes:
   ```powershell
   git tag -a v1.0.1 -m "v1.0.1: what changed"
   ```
5. Push the branch and the tag:
   ```powershell
   git push origin main
   ```
   ```powershell
   git push origin v1.0.1
   ```
6. The `release` workflow runs all tests, checks that the tag matches
   `__version__`, builds the zip and publishes the GitHub release. Check it at
   https://github.com/mttfntn/octane-fast-startup-blender/actions.

To support another Blender version, add it to the CI (`BLENDER_VERSION`, the
SHA-256 from `https://download.blender.org/release/BlenderX.Y/blender-X.Y.Z.sha256`),
update `SUPPORTED_BLENDER`, the badge and the requirements, and test with real Octane.

## 8. Bringing in Octane updates

This is not a fork, so there is no upstream code to merge. "Upstream" here means
new Octane add-on versions, which may rename what the script wraps.

1. Install the new Octane add-on (keep a backup of the old folder).
2. Run `check.py` (in a scratch profile).
3. If `NOT WORKING`, read the new add-on's `core/client.py`, `utils/ocio.py`,
   `core/resource_cache.py`, `handlers.py`; profile a headless startup + New File with
   `cProfile` to find slow native calls (`octane_blender.*` functions waiting on the server).
4. Update `TARGET`, the wrapped method names, or add a newly slow method; update the
   stub in `tests/stub_octane` to match the new shape; run all tests.

Prompt for an AI assistant (paste into a session opened in this folder):

```text
Octane published an update. Read AGENTS.md and HANDOVER.md first.
1. Run check.py against a scratch profile with the new Octane add-on and tell me the result.
2. If it is not OK, read the new add-on code (core/client.py, utils/ocio.py,
   core/resource_cache.py, handlers.py) and find what changed.
3. Profile a headless startup + New File with cProfile in a scratch profile
   (BLENDER_USER_RESOURCES). Never use my running Blender or my real profile.
4. Update startup/octane_fast_start.py and tests/stub_octane so the slow calls are
   skipped while the server is offline and pass through unchanged while it is online.
5. Run the unit tests, tests/compare.py --git HEAD, tests/blender_test.py and check.py.
Do not modify the Octane add-on's own files.
```

## 9. Things to know

- **v1.0.0 bug fix:** before v1.0.0 the server address was always
  `127.0.0.1:50051`, because the preferences were read too early and the error was
  swallowed. Users with a custom port or a remote server had every call skipped.
  Fixed; `tests/compare.py` lists it as an expected difference.
- **Octane 32.2 changed the picture.** Octane now asks `is_server_reachable()`
  (a 200 ms gRPC probe, itself a wrapped `utils_function(TEST_CONNECTION)` call)
  before `API_START` and the OCIO update. With the script active that probe is
  skipped too, so Octane itself never sends `API_START` while offline, and the
  script's `pending_start` stays `False`. When the server appears later, the script
  then runs only the OCIO update and resource reset. Without the script, Octane
  32.2 behaves the same way here.
- `check.py` reads `_state["skipped"]` and `_state["up"]` from the script; keep
  those names.
- `unregister()` only removes the import hook; the wrappers, thread and timer stay
  until Blender restarts (startup-script reloads are rare).
- Blender runs the add-on's load_post handler for the startup file too, so a
  headless start makes the same calls as one File > New.

## 10. Known limits

- Depends on Octane internals (module `octane.core.client`, class `OctaneBlender`,
  three method names). Any Octane update can break it; `check.py` detects that.
- Only "is something listening on the port" is checked (a TCP connect with a 50 ms
  timeout). A slow remote server may be seen as offline; something else on that
  port would be seen as the server.
- `localhost` is probed as IPv4 `127.0.0.1`. A server listening only on IPv6
  would look offline. Not tested with a real Octane Server.
- **Not verified with a real Octane Server running.** The online and
  "comes online" paths are tested with a stand-in listener, and the stub
  add-on. Do one real Octane render after installing to confirm.
- Only Blender 5.3 is supported and tested.
