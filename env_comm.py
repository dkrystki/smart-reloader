from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
from envo import VirtualEnv  # noqa: F401
from envo import (
    Namespace,
    Plugin,
    Raw,
    UserEnv,
    boot_code,
    command,
    context,
    logger,
    oncreate,
    ondestroy,
    onload,
    onstderr,
    onstdout,
    onunload,
    postcmd,
    precmd,
    run,
)

# Declare your command namespaces here
# like this:
# my_namespace = command(namespace="my_namespace")


class EnvoCommEnv(UserEnv):  # type: ignore
    class Meta(UserEnv.Meta):  # type: ignore
        root: str = Path(__file__).parent.absolute()
        stage: str = "comm"
        emoji: str = "👌"
        parents: List[str] = []
        plugins: List[Plugin] = []
        name: str = "smart-reloader"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    poetry_ver: str

    def __init__(self) -> None:
        self.poetry_ver = "1.0.5"

    @command
    def bootstrap(self):
        run(f"pip install poetry=={self.poetry_ver}")
        run("poetry install")

    @boot_code
    def __boot(self) -> List[str]:
        return []


Env = EnvoCommEnv
