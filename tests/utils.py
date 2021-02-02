import builtins
import sys
from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from textwrap import dedent
from types import ModuleType
from typing import Any, List, Optional

import pytest

import smartreload
from smartreload import dependency_watcher

logger = getLogger(__name__)


def load_module(name: str) -> Any:
    module = builtins.__import__(name)
    return module


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox):
        sys.path.insert(0, str(sandbox.parent))
        dependency_watcher._reset()

        for n, m in sys.modules.copy().items():
            if hasattr(m, "__file__") and Path(m.__file__).parent == sandbox:
                sys.modules.pop(n)

        yield

        sys.path.remove(str(sandbox.parent))


class WhatStringNotFound(Exception):
    pass


@dataclass
class Module:
    path: str
    source: str
    device: Optional[Any] = None

    def __post_init__(self) -> None:
        self._path = Path(self.path).absolute()
        self._fixed_source = dedent(self.source)
        self.write()

    def rewrite(self, new_source: str) -> None:
        self._fixed_source = dedent(new_source)
        self.write()

    def append(self, source: str) -> None:
        self._fixed_source += dedent(source)
        self.write()

    def write(self):
        self._path.write_text(self._fixed_source)

    def replace(self, what: str, to: str) -> None:
        if what not in self.source:
            raise WhatStringNotFound()

        self._fixed_source = self._fixed_source.replace(what, to)
        self.write()

    def delete(self, what: str) -> None:
        self.replace(what, "")

    def load(self) -> None:
        if self._path.stem != "__init__":
            name = self._path.stem
        else:
            name = self._path.parent.absolute().stem

        self.device = load_module(name)

    def assert_obj_in(self, obj_name: str) -> None:
        assert obj_name in self.device.__dict__

    def assert_obj_not_in(self, obj_name: str) -> None:
        assert obj_name not in self.device.__dict__


@dataclass
class Reloader:
    root: Path
    device: smartreload.PartialReloader = field(init=False, default=None)

    def reload(self, module: Module) -> None:
        self.device = smartreload.PartialReloader(self.root, logger)
        self.device.reload(str(module._path))

    def assert_actions(self, *actions: str) -> None:
        actions_str = tuple(repr(a) for a in self.device.applied_actions)
        assert actions_str == actions
