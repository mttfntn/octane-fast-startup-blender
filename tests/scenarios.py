"""Behaviour scenarios for Octane Fast Start, run without Blender.

Usage:  python tests/scenarios.py <path/to/octane_fast_start.py> <scenario>
Prints one JSON object: a trace of what the wrapped Octane methods returned,
which calls reached the (stub) Octane client, and the script's state.
Each scenario runs in its own process (fresh imports, no leftover threads).
Used by test_fast_start.py (assertions) and compare.py (old vs new diff).
"""
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 50051


# ---- fake bpy: just the parts the script touches --------------------------

class _Timers:
    def __init__(self):
        self.fns = []

    def register(self, fn, first_interval=0.0, persistent=False):
        self.fns.append(fn)

    def is_registered(self, fn):
        return fn in self.fns

    def tick(self):
        for fn in list(self.fns):
            fn()


def install_fake_bpy():
    bpy = types.ModuleType("bpy")
    bpy.app = types.SimpleNamespace(timers=_Timers())
    bpy.context = types.SimpleNamespace(preferences=types.SimpleNamespace(addons={}))
    sys.modules["bpy"] = bpy
    return bpy


def set_prefs(bpy, address="127.0.0.1", port=DEFAULT_PORT):
    """What Octane's register() does: from now on its preferences exist."""
    prefs = types.SimpleNamespace(octane_server_address=address, octane_addon_server_port=port)
    bpy.context.preferences.addons["octane"] = types.SimpleNamespace(preferences=prefs)


# ---- a fake Octane Server: something listening on a port ------------------

class Listener:
    def __init__(self, port):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", port))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.open = True
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while self.open:
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except OSError:
                return

    def close(self):
        self.open = False
        self.sock.close()


def port_in_use(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.05):
            return True
    except OSError:
        return False


# ---- helpers ---------------------------------------------------------------

def load_fast_start(path):
    spec = importlib.util.spec_from_file_location("octane_fast_start", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["octane_fast_start"] = mod
    spec.loader.exec_module(mod)
    return mod


def octane_register(bpy, **prefs):
    """Import the stub add-on and run what its register() does."""
    import octane  # noqa: F401  (imports octane.core.client -> the hook patches it)
    from octane.core.client import OctaneBlender
    from octane.utils import consts
    set_prefs(bpy, **prefs)
    return OctaneBlender().utils_function(consts.UtilsFunctionType.API_START, "", -1)


def load_post():
    """What the add-on's load_post handler does on every New / Open."""
    from octane.utils import ocio
    from octane.core import resource_cache
    return [ocio.update_ocio_info(), resource_cache.reset_resource_cache()]


def wait_for_prober(fs, up, seconds=8.0):
    """Wait until the background prober has seen the server state `up`
    (twice in a row when `up` is True, as the script's timer requires)."""
    end = time.time() + seconds
    while time.time() < end:
        if fs._state["up"] is up and (not up or fs._state.get("streak", 0) >= 2):
            return True
        time.sleep(0.1)
    return False


# ---- scenarios -------------------------------------------------------------

SCENARIOS = ["offline_default", "online_default", "offline_then_online", "online_then_offline",
             "custom_port_online", "localhost_alias", "reload", "double_register"]


def run(fs_path, name):
    if name not in SCENARIOS:
        raise SystemExit(f"unknown scenario {name}")
    os.environ["OCTANE_STUB_DELAY"] = "0.3"
    sys.path.insert(0, os.path.join(HERE, "stub_octane"))
    bpy = install_fake_bpy()
    if port_in_use(DEFAULT_PORT):
        return {"scenario": name, "skip": f"port {DEFAULT_PORT} is in use (Octane Server running?)"}
    trace = {"scenario": name, "results": []}

    fs = None
    listener = None
    if name != "reload":
        fs = load_fast_start(fs_path)
        fs.register()

    if name == "offline_default":
        trace["results"].append(octane_register(bpy))
        trace["results"] += load_post() + load_post()

    elif name == "online_default":
        listener = Listener(DEFAULT_PORT)
        trace["results"].append(octane_register(bpy))
        trace["results"] += load_post()

    elif name == "offline_then_online":
        trace["results"].append(octane_register(bpy))
        trace["results"] += load_post()
        listener = Listener(DEFAULT_PORT)
        trace["prober_saw_online"] = wait_for_prober(fs, True)
        bpy.app.timers.tick()
        bpy.app.timers.tick()  # a second tick must not initialise again
        trace["results"] += load_post()

    elif name == "online_then_offline":
        listener = Listener(DEFAULT_PORT)
        trace["results"].append(octane_register(bpy))
        listener.close()
        listener = None
        trace["prober_saw_offline"] = wait_for_prober(fs, False)
        bpy.app.timers.tick()
        trace["results"] += load_post()

    elif name == "custom_port_online":
        # Server on a non-default port (set in Octane's preferences); 50051 stays closed.
        listener = Listener(0)
        trace["results"].append(octane_register(bpy, port=listener.port))
        trace["results"] += load_post()

    elif name == "localhost_alias":
        listener = Listener(DEFAULT_PORT)
        trace["results"].append(octane_register(bpy, address="localhost"))
        trace["results"] += load_post()

    elif name == "reload":
        # Octane was imported before the script registered (script reload). Offline.
        import octane  # noqa: F401
        fs = load_fast_start(fs_path)
        fs.register()
        from octane.core.client import OctaneBlender
        from octane.utils import consts
        set_prefs(bpy)
        trace["results"].append(OctaneBlender().utils_function(consts.UtilsFunctionType.API_START, "", -1))
        trace["results"] += load_post()

    elif name == "double_register":
        fs.register()
        listener = Listener(DEFAULT_PORT)
        trace["results"].append(octane_register(bpy))
        fs.register()
        trace["results"] += load_post()

    from octane.core import client
    trace["calls_reaching_octane"] = client.CALLS
    trace["patched"] = getattr(client.OctaneBlender, "_fast_start_patched", False)
    trace["skipped"] = fs._state["skipped"]
    trace["pending_start"] = fs._state["pending_start"]
    trace["finders_installed"] = sum(1 for f in sys.meta_path if type(f).__name__ == "_Finder")
    if listener:
        listener.close()
    return trace


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1], sys.argv[2])))
