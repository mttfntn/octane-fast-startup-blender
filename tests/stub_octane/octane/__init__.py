"""Stand-in for the OTOY Octane add-on, for tests only (contains no OTOY code).

It reproduces just the shape Octane Fast Start relies on:
  * the package imports octane.core.client at import time, BEFORE register()
    creates the add-on preferences (the real add-on does the same);
  * register() sends API_START; a load_post handler sends the OCIO update and
    resets the resource cache, like the real add-on does on every file load;
  * each of those requests waits OCTANE_STUB_DELAY seconds (default 1.0) when
    nothing listens on the server port, like the real gRPC client does.
Works as a Blender legacy add-on and, without Blender, as a plain package.
"""
bl_info = {
    "name": "Octane stub (Octane Fast Start tests)",
    "author": "Octane Fast Start tests",
    "version": (0, 0, 1),
    "blender": (4, 2, 0),
    "category": "Render",
}

from octane.core.client import OctaneBlender  # noqa: E402  (import order matters, see above)

try:
    import bpy.types  # only inside Blender; a fake bpy module in tests has no .types
    import bpy
except ImportError:
    bpy = None

if bpy is not None:
    class OctaneStubPreferences(bpy.types.AddonPreferences):
        bl_idname = __name__
        octane_server_address: bpy.props.StringProperty(default="127.0.0.1")
        octane_addon_server_port: bpy.props.IntProperty(default=50051)

    @bpy.app.handlers.persistent
    def octane_load_post_handler(_arg):
        from octane.utils import ocio
        from octane.core import resource_cache
        ocio.update_ocio_info()
        resource_cache.reset_resource_cache()

    def register():
        bpy.utils.register_class(OctaneStubPreferences)
        from octane.utils import consts
        OctaneBlender().utils_function(consts.UtilsFunctionType.API_START, "", -1)
        bpy.app.handlers.load_post.append(octane_load_post_handler)

    def unregister():
        if octane_load_post_handler in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(octane_load_post_handler)
        bpy.utils.unregister_class(OctaneStubPreferences)
