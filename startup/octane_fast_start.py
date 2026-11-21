"""Octane Fast Start  (Blender startup script)

Problem: when the Octane Server is not running, the Octane add-on still sends
requests to it at startup and on EVERY file load (New / Open). Each request
waits for a connection timeout before failing (~4 s each with add-on 31.7;
32.2 has its own 200 ms probe but still pays ~0.8 s per file load), so Blender
starts and opens files slowly.

Fix: before each slow server call, check in ~1 ms whether the server port is
listening. If it is not, skip the call (Octane already handles a failed call,
it just takes a while to find out). When the server comes online, the skipped
start-up work (API start, OCIO colour info, resource reset) runs automatically.

How the pieces fit together:
  register()        Blender calls this at startup, before add-ons load. It puts
                    _Finder on sys.meta_path.
  _Finder           Import hook: right after Octane imports octane.core.client,
                    it calls patch() on that module.
  patch()           Wraps three OctaneBlender methods with a "server up?" check
                    and starts the background prober and the Blender timer.
  _watch()          Background thread: probes the port every 2 s (never blocks UI).
  _timer()          Blender timer (main thread): reads the server address once
                    Octane's preferences exist, and runs _on_server_online()
                    when the server appears.

Nothing in the Octane add-on itself is modified; delete this file to undo.
Install: add the repository folder to Blender's Preferences > File Paths >
Script Directories, or copy this file to <Blender user scripts>/startup/.
"""

import importlib.abc
import socket
import sys
import threading
import time

TARGET = "octane.core.client"  # Octane module that defines OctaneBlender

# Shared state. Written by the main thread and by the _watch() thread; each
# value is a single assignment, so no lock is needed.
_state = {
    "host": "127.0.0.1",
    "port": 50051,
    "address_read": False,  # True once the address came from Octane's preferences
    "up": None,          # None = unknown, True/False = last probe result
    "skipped": 0,        # number of skipped server calls (reported by check.py)
    "pending_start": False,  # API_START was skipped and must be sent later
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
    """Last known server state; reads the address / probes once if still unknown.

    Called from the wrapped Octane methods (main thread)."""
    if not _state["address_read"] and threading.current_thread() is threading.main_thread():
        if _read_server_address():
            _state["up"] = None  # the address may have changed: probe it again
    if _state["up"] is None:
        _state["up"] = _probe()
    return _state["up"]


def _watch():
    # Background thread: keep the "is server up" flag fresh without blocking the UI.
    # "streak" counts consecutive successful probes (used by _timer()).
    while not _state["stop"]:
        up = _probe()
        _state["up"] = up
        _state["streak"] = _state.get("streak", 0) + 1 if up else 0
        time.sleep(2.0)


def _read_server_address():
    """Copy the server host/port from Octane's add-on preferences into _state.

    Returns False while those preferences do not exist yet: Octane imports
    octane.core.client (when patch() runs) before its register() creates them,
    so the first successful read happens at the first wrapped call or timer tick.
    Main thread only (it reads bpy data)."""
    try:
        import bpy
        prefs = bpy.context.preferences.addons["octane"].preferences
        host = prefs.octane_server_address or "127.0.0.1"
        port = int(prefs.octane_addon_server_port)
    except Exception:
        return False
    _state["host"] = "127.0.0.1" if host in ("", "localhost") else host
    _state["port"] = port
    _state["address_read"] = True
    return True


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
    """Blender timer, every 2 s: notice the server coming online (main thread)."""
    if not _state["address_read"]:
        _read_server_address()  # the background prober uses the new address next round
    up = bool(_state["up"])
    if not up:
        _state["was_up"] = False
    elif not _state["was_up"] and _state.get("streak", 0) >= 2:
        # online for 2 consecutive probes: server has finished starting
        _on_server_online()
        _state["was_up"] = True
    return 2.0


def patch(mod):
    """Wrap the slow OctaneBlender methods of the freshly imported client module.

    Each wrapper skips the real call (returning what a failed call returns:
    "" or None) while the server port is closed, and calls the original,
    unchanged, while it is open. Safe to call twice."""
    C = getattr(mod, "OctaneBlender", None)
    if C is None or getattr(C, "_fast_start_patched", False):
        return
    # client.py imports consts at its top, so this import cannot fail here.
    from octane.utils import consts
    api_start = consts.UtilsFunctionType.API_START

    _read_server_address()  # normally too early (see its docstring); retried later

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
        pass  # outside Blender (unit tests): no timer
    _log("active - Octane Server is %s" % ("online" if _state["was_up"] else
                                           "offline, slow server calls will be skipped"))


class _Finder(importlib.abc.MetaPathFinder):
    """Patch octane.core.client right after it is imported."""

    def find_spec(self, name, path, target=None):
        if name != TARGET:
            return None
        # Ask the other finders for the real spec, then wrap its loader so
        # patch() runs as soon as the module has executed.
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
    """Called by Blender for scripts in scripts/startup, before add-ons load."""
    if _finder not in sys.meta_path:
        sys.meta_path.insert(0, _finder)
    if TARGET in sys.modules:  # Octane already loaded (e.g. script reload)
        patch(sys.modules[TARGET])


def unregister():
    """Called by Blender when startup scripts are reloaded. Removes the import
    hook only; the wrapped methods, the prober thread and the timer stay
    active until Blender restarts."""
    if _finder in sys.meta_path:
        sys.meta_path.remove(_finder)
