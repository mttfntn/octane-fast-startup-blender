# Octane Fast Start

[![Blender](https://img.shields.io/badge/Blender-5.3-orange?logo=blender&logoColor=white)](https://www.blender.org/download/)
[![Release](https://img.shields.io/badge/release-v1.0.0-blue)](https://github.com/mttfntn/octane-fast-startup-blender/releases)
[![tests](https://github.com/mttfntn/octane-fast-startup-blender/actions/workflows/tests.yml/badge.svg)](https://github.com/mttfntn/octane-fast-startup-blender/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)](startup/octane_fast_start.py)
[![Works with](https://img.shields.io/badge/works%20with-OctaneRender%20for%20Blender%20(OTOY)-lightgrey)](https://home.otoy.com/render/octane-render/)

A Blender startup script that makes Blender start and open files quickly
**while the Octane add-on stays enabled but the Octane Server is not running**.

When no Octane Server is running, the Octane add-on still sends requests to it
at startup and on **every** File > New / Open, and each request waits for a
connection timeout. Octane Fast Start checks in about 1 ms whether the server
port is open and skips those requests while it isn't. When the server comes
online, the skipped start-up work runs automatically. Octane's own files are
never modified.

> Unofficial. Not affiliated with or endorsed by OTOY Inc. OctaneRender is a
> trademark of OTOY Inc. This repository contains no OTOY code.

## Measurements

Blender 5.3.0, Octane Server not running, headless Blender in a scratch
profile with only the Octane add-on enabled (`check.py`, 2026-11-21):

| Octane add-on | Startup, without → with | File > New, without → with |
|---|---|---|
| 31.7.0 | ~28 s → ~2.0 s | 8.1 s → 0.01 s |
| 32.2.0 alpha | ~5.3 s → ~2.1 s | 0.79 s → 0.01 s |

Octane 32.2 added its own short server probe, so the gain is smaller there
but still about 2.5× at startup and 80× per file load. In a full user setup
with the 31.7 add-on (GUI Blender, many add-ons), startup went from ~20 s to ~2.7 s.

## Requirements

- **Blender 5.3** (the only version tested; see [HANDOVER.md](HANDOVER.md) to add more)
- The OctaneRender for Blender add-on (tested with 31.7.0 and 32.2.0 alpha)
- Windows is what it was built and measured on; the script itself is
  plain Python (CI runs the unit tests on Linux and Windows, and the Blender
  test on Linux with a stand-in for Octane)

## Install

**Option A: from a release zip (recommended)**

1. Download `octane-fast-start-X.Y.Z.zip` from
   [Releases](https://github.com/mttfntn/octane-fast-startup-blender/releases)
   and unzip it somewhere permanent, e.g. `Documents\Blender\octane-fast-start`.
2. In Blender: **Edit > Preferences > File Paths > Script Directories > Add**,
   and choose the unzipped `octane-fast-start` folder (the one that contains `startup\`).
3. Save preferences (if auto-save is off) and **restart Blender**.

To update, replace the folder's contents with a newer release. Using a
`git clone` of this repo as the script directory works the same way.

**Option B: copy one file**

Copy `startup/octane_fast_start.py` to
`%APPDATA%\Blender Foundation\Blender\5.3\scripts\startup\` and restart Blender.
Repeat for each new Blender version folder.

**Check it works:** Window > Toggle System Console shows
`[Octane Fast Start] active - Octane Server is ...` at startup. Or run:

```powershell
python check.py
```

(`check.py` takes the path to `blender.exe` as an argument if Blender is not in
`C:\Program Files\Blender Foundation\Blender 5.3\`.) `RESULT: OK` means it works.

**Uninstall:** remove the script directory from Preferences (option A) or
delete the copied file (option B), then restart Blender.

## After an Octane update

Run `python check.py`. If it says `NOT WORKING`, Octane renamed something the
script relies on (`octane.core.client.OctaneBlender` and its methods
`utils_function`, `reset_render`, `update_server_settings`). Until it is fixed,
remove the script: Blender then behaves exactly as before, only slower.
[HANDOVER.md](HANDOVER.md) explains how to adapt the script.

## How it works (short)

1. Blender loads startup scripts **before** add-ons. The script installs an
   import hook that patches `octane.core.client` the moment Octane imports it.
2. Three `OctaneBlender` methods are wrapped. When nothing is listening on the
   server port (taken from Octane's preferences, default `127.0.0.1:50051`), the
   call is skipped and returns what a failed call returns. When the port is
   open, the original method runs, unchanged.
3. A background thread re-checks the port every 2 s. When the server has been up
   for two checks in a row, a Blender timer runs the skipped start-up work.

## Documentation

- [HANDOVER.md](HANDOVER.md): full guide for maintainers (code layout, tests, releases, limits)
- [AGENTS.md](AGENTS.md): compact notes for AI coding assistants

## License

[GPL-3.0-or-later](LICENSE), the same license family as Blender.
