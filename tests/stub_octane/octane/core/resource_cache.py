"""Stub of octane.core.resource_cache."""


def reset_resource_cache():
    from octane.core.client import OctaneBlender
    OctaneBlender().reset_render()
    return OctaneBlender().update_server_settings(1, True)
