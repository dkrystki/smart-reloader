import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional


__all__ = []

STICKYBEAK_PORT = 5287

enabled = "SMART_RELOADER_E2E_TEST" in os.environ

project_root = Path(__file__).parent


class Debugger:
    stopped = False

    @classmethod
    def pause(cls):
        cls.stopped = True

        while cls.stopped:
            pass

    @classmethod
    def wait_until_paused(cls):
        while not cls.stopped:
            pass

    @classmethod
    def resume(cls):
        cls.stopped = False
