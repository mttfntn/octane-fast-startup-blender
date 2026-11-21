"""Octane Fast Start  (Blender startup script)

Problem: when the Octane Server is not running, the Octane add-on still sends
requests to it at startup and on EVERY file load (New / Open). Each request
waits ~4 s before failing, so Blender takes ~20 s to start and ~8 s per file.

Fix: before each slow server call, check in ~1 ms whether the server port is
listening. If it is not, skip the call (Octane already handles a failed call,
it just takes 4 s to find out). When the server comes online, the skipped
start-up work (API start, OCIO colour info, resource reset) runs automatically.

Nothing in the Octane add-on itself is modified; delete this file to undo.
Install location: <Blender user scripts>/startup/octane_fast_start.py
"""

import importlib.abc
import socket
import sys
import threading
import time

TARGET = "octane.core.client"
API_START = 1  # consts.UtilsFunctionType.API_START (resolved at patch time)

_state = {
    "host": "127.0.0.1",
    "port": 50051,
    "up": None,          # None = unknown, True/False = last probe result
    "skipped": 0,
    "pending_start": False,
    "was_up": False,
    "thread": None,
    "stop": False,
}


def _log(msg):
    print(f"[Octane Fast Start] {msg}")


def _probe():
    """True if something is listening on the Octane add-on server port."""
    try:
        with socket.create_connection((_state["host"], _state["port"]), timeout=0.05):
            return True
    except OSError:
        return False


def _server_up():
    if _state["up"] is None:
        _state["up"] = _probe()
    return _state["up"]


def _watch():
    # Background thread: keep the "is server up" flag fresh without blocking the UI.
    while not _state["stop"]:
        up = _probe()
        _state["up"] = up
        _state["streak"] = _state.get("streak", 0) + 1 if up else 0
        time.sleep(2.0)


def _read_server_address():
    try:
        import bpy
        prefs = bpy.context.preferences.addons["octane"].preferences
        host = prefs.octane_server_address or "127.0.0.1"
        _state["port"] = int(prefs.octane_addon_server_port)
    except Exception:
        host = "127.0.0.1"
    _state["host"] = "127.0.0.1" if host in ("", "localhost") else host


def _on_server_online():
    """Run the start-up work Octane skipped while the server was offline."""
    try:
        from octane.core.client import OctaneBlender
        from octane.utils import consts
        ob = OctaneBlender()
        if _state["pending_start"]:
            ob.utils_function(consts.UtilsFunctionType.API_START, "", -1)
            _state["pending_start"] = False
        from octane.utils import ocio
        ocio.update_ocio_info()
        from octane.core import resource_cache
        resource_cache.reset_resource_cache()
        _log("Octane Server online - Octane initialised")
    except Exception as e:
        _log(f"post-connect init failed: {e}")


def _timer():
    up = bool(_state["up"])
    if not up:
        _state["was_up"] = False
    elif not _state["was_up"] and _state.get("streak", 0) >= 2:
        # online for 2 consecutive probes: server has finished starting
        _on_server_online()
        _state["was_up"] = True
    return 2.0


def patch(mod):
    C = getattr(mod, "OctaneBlender", None)
    if C is None or getattr(C, "_fast_start_patched", False):
        return
    try:
        from octane.utils import consts
        api_start = consts.UtilsFunctionType.API_START
    except Exception:
        api_start = API_START

    _read_server_address()

    orig_utils = C.utils_function
    orig_reset = C.reset_render
    orig_settings = C.update_server_settings

    def utils_function(self, command_type, data, timeout=-1, client_name=None):
        if not _server_up():
            _state["skipped"] += 1
            if command_type == api_start:
                _state["pending_start"] = True
            return ""
        return orig_utils(self, command_type, data, timeout, client_name)

    def reset_render(self):
        if not _server_up():
            _state["skipped"] += 1
            return None
        return orig_reset(self)

    def update_server_settings(self, *args, **kwargs):
        if not _server_up():
            _state["skipped"] += 1
            return None
        return orig_settings(self, *args, **kwargs)

    C.utils_function = utils_function
    C.reset_render = reset_render
    C.update_server_settings = update_server_settings
    C._fast_start_patched = True

    _state["was_up"] = _server_up()
    if _state["thread"] is None:
        t = threading.Thread(target=_watch, name="octane_fast_start", daemon=True)
        t.start()
        _state["thread"] = t
    try:
        import bpy
        if not bpy.app.timers.is_registered(_timer):
            bpy.app.timers.register(_timer, first_interval=2.0, persistent=True)
    except Exception:
        pass
    _log("active - Octane Server is %s" % ("online" if _state["was_up"] else
                                           "offline, slow server calls will be skipped"))


class _Finder(importlib.abc.MetaPathFinder):
    """Patch octane.core.client right after it is imported."""

    def find_spec(self, name, path, target=None):
        if name != TARGET:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(name, path, target)
            if spec is not None:
                break
        else:
            return None
        loader = spec.loader
        orig_exec = loader.exec_module

        def exec_module(module):
            orig_exec(module)
            try:
                patch(module)
            except Exception as e:
                _log(f"patch failed: {e}")

        loader.exec_module = exec_module
        return spec


_finder = _Finder()


def register():
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)
    if TARGET in sys.modules:  # Octane already loaded (e.g. script reload)
        patch(sys.modules[TARGET])


def unregister():
    if _finder in sys.meta_path:
        sys.meta_path.remove(_finder)
