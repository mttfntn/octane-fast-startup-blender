"""Stub of octane.utils.ocio."""


def update_ocio_info():
    from octane.core.client import OctaneBlender
    from octane.utils import consts
    return OctaneBlender().utils_function(consts.UtilsFunctionType.UPDATE_OCIO_SETTINGS, "<ocio/>")
