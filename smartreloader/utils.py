import ctypes
from types import FrameType


def apply_changes_to_frame(frame_obj: FrameType):
    ctypes.pythonapi.PyFrame_LocalsToFast(
        ctypes.py_object(frame_obj),
        ctypes.c_int(1))

