"""Stub of octane.core.client: an OctaneBlender class with the three methods
Octane Fast Start wraps. Every call is recorded in CALLS."""
import os
import socket
import time

from octane.utils import consts  # the real client.py imports consts at its top too

CALLS = []


def _port():
    try:
        import bpy
        return int(bpy.context.preferences.addons["octane"].preferences.octane_addon_server_port)
    except Exception:
        return int(os.environ.get("OCTANE_STUB_PORT", "50051"))


def _wait_if_no_server():
    """Simulate the real client's connection timeout when no server listens."""
    try:
        with socket.create_connection(("127.0.0.1", _port()), timeout=0.05):
            return
    except OSError:
        time.sleep(float(os.environ.get("OCTANE_STUB_DELAY", "1.0")))


class OctaneBlender:
    def utils_function(self, command_type, data, timeout=-1, client_name=None):
        CALLS.append(["utils_function", command_type, data, timeout, client_name])
        _wait_if_no_server()
        return "<response result='1' content='stub'/>"

    def reset_render(self):
        CALLS.append(["reset_render"])
        _wait_if_no_server()
        return "reset"

    def update_server_settings(self, resource_cache_type, update_shared_surface_device_id=False,
                               tonemap_buffer_type=0, color_space_type=0):
        CALLS.append(["update_server_settings", resource_cache_type, update_shared_surface_device_id,
                      tonemap_buffer_type, color_space_type])
        _wait_if_no_server()
        return "settings"
