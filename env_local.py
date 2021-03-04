from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

import envo  # noqa: F401
from envo import UserEnv  # noqa: F401
from envo import (
    BaseEnv,
    Namespace,
    Plugin,
    Raw,
    VirtualEnv,
    boot_code,
    command,
    console,
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

localci = Namespace(name="localci")


class EnvoLocalEnv(UserEnv):  # type: ignore
    class Meta(UserEnv.Meta):  # type: ignore
        root: Path = Path(__file__).parent.absolute()
        stage: str = "local"
        emoji: str = "🐣"
        parents: List[str] = ["env_comm.py"]
        plugins: List[Plugin] = [VirtualEnv]
        name: str = "smart-reloader"
        version: str = "0.1.0"
        watch_files: List[str] = []
        ignore_files: List[str] = []

    def __init__(self) -> None:
        pass

    @command
    def test(self) -> None:
        logger.info("Running tests")
        run("pytest tests -v")

    @command
    def flake(self) -> None:
        self.black()
        run("flake8")

    @command
    def mypy(self) -> None:
        logger.info("Running mypy")
        run("mypy envo")

    @command
    def black(self) -> None:
        with console.status("Running black and isort..."):
            run("isort .", print_output=False)
            run("black .", print_output=False)

    @command
    def ci(self) -> None:
        self.flake()
        self.mypy()
        self.test()

    @localci.command
    def __flake(self) -> None:
        run("circleci local execute --job flake8")


Env = EnvoLocalEnv
