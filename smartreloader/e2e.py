import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional

__all__ = []

STICKYBEAK_PORT = 5175

enabled = "SMART_RELOADER_E2E_TEST" in os.environ

project_root = Path(__file__).parent

if TYPE_CHECKING:
    import stickybeak

server: Optional["stickybeak.Server"] = None


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


def start():
    global server
    import stickybeak

    server = stickybeak.Server(project_root, STICKYBEAK_PORT)
    server.start()
