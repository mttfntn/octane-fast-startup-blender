# AGENTS.md: Octane Fast Start

Compact notes for AI coding assistants. Human guide: [HANDOVER.md](HANDOVER.md).

## What
Blender 5.3 startup script `startup/octane_fast_start.py` (stdlib only). It wraps
`octane.core.client.OctaneBlender.{utils_function, reset_render, update_server_settings}`
so they are skipped (returning `""` / `None`) while nothing listens on the Octane
server port, and pass through unchanged otherwise. It never edits Octane's files.
Unofficial; repo contains no OTOY code.

## Commands
```powershell
python -m unittest discover -s tests -v                      # 8 tests, no Blender needed
python tests/compare.py --git HEAD                           # behaviour diff old vs working copy
python tests/blender_test.py "C:\Program Files\Blender Foundation\Blender 5.3\blender.exe"
python tools/build.py [--expect-version vX.Y.Z]              # -> dist/octane-fast-start-X.Y.Z.zip
$env:BLENDER_USER_RESOURCES="<scratch>"; python check.py     # real Octane, scratch profile
```

## Architecture / data flow
`register()` (Blender, before add-ons) → `_Finder` on `sys.meta_path` → when Octane
imports `octane.core.client`, the loader's `exec_module` is wrapped → `patch(module)`
wraps the 3 methods, starts thread `_watch()` (TCP probe every 2 s → `_state["up"]`,
`_state["streak"]`) and `bpy.app.timers` `_timer()` (main thread: retries
`_read_server_address()`; on `streak >= 2` after offline → `_on_server_online()`:
`API_START` if `pending_start`, `ocio.update_ocio_info()`,
`resource_cache.reset_resource_cache()`).
State lives in module dict `_state`; `check.py` reads `_state["up"]` and `_state["skipped"]`.

## Rules and pitfalls
- Never test in the user's running Blender or real profile. Use `blender -b` with
  `BLENDER_USER_RESOURCES=<temp dir>` (holds `config/`, `scripts/addons/`, `scripts/startup/`).
- Octane imports `octane.core.client` at package import, **before** its `register()`
  creates its add-on preferences. Anything reading `bpy.context.preferences.addons["octane"]`
  during `patch()` fails; read it later on the main thread. (This was the v1.0.0 bug.)
- Don't read bpy data from the `_watch()` thread.
- `client.py` imports `consts` at its top (31.7 and 32.2), so `octane.utils.consts`
  is importable inside `patch()`. `API_START` is 303.
- Octane 32.2 has its own `client.is_server_reachable()` (via `utils_function(TEST_CONNECTION)`,
  which the script also wraps); 31.7 does not. Behaviour differs per version; see HANDOVER §9.
- Blender fires `load_post` for the startup file too: a headless start = startup calls + one New File.
- No Blender operators/panels exist. If you add one, use `#` comments on the class, not a
  docstring (Blender shows it as the tooltip).
- Keep `tests/stub_octane` in sync with the real add-on shape when Octane changes.
- `scenarios.py` uses port 50051 and skips if it is busy (a real Octane Server running).

## How changes were verified (v1.0.0)
- Unit tests: new 8/8; original script 7/8 (fails only the custom-port regression test).
- `compare.py --git e67912f`, 2 runs per side: all 8 scenarios identical except
  `custom_port_online` (intended fix); runs of the same file identical (no noise).
- `blender_test.py` on Blender 5.3.0 (Windows): no_fix New File 3.2 s, not patched;
  startup_copy / script_directory 0.007 s, patched; online 7 calls pass, 0 skipped.
- `check.py` with real Octane 31.7.0 and 32.2.0 alpha in scratch profiles, original vs new:
  identical (patched, same skipped count, New File 0.01 s).

## Release checklist
1. Bump `__version__` in `startup/octane_fast_start.py`.
2. Update the static release badge (and measurements if changed) in `README.md`.
3. Run all commands above; commit.
4. `git tag -a vX.Y.Z -m "<release notes>"`; `git push origin main`; `git push origin vX.Y.Z`.
5. Workflow `release.yml`: tests → fetch tag → build with `--expect-version` → `gh release create`
   with the tag message as notes and the zip attached. Check the Actions run.

## Git setup
- Remote `origin` = https://github.com/mttfntn/octane-fast-startup-blender (public), branch `main`.
- `.gitattributes`: LF line endings. `dist/` and `__pycache__/` are ignored.
- Commit history starts with the original files (`e67912f`), so `git show e67912f:octane_fast_start.py`
  is the pre-handover script.
- Repo is public → release, license and language badges are live; the Blender, Python and "works with" badges are static.
