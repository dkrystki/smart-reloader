import builtins
import sys
import dill
from copy import copy, deepcopy

from dataclasses import dataclass, field
from logging import getLogger
from pathlib import Path
from textwrap import dedent
from typing import Any, Optional, Dict

import pytest

import smartreload

logger = getLogger(__name__)

from smartreload import dependency_watcher


def load_module(name: str) -> Any:
    module = builtins.__import__(name)
    # TODO: this shouldn't be needed
    # dependency_watcher.import_order.insert(0, module.__file__)
    return module


class TestBase:
    @pytest.fixture(autouse=True)
    def setup(self, sandbox, modules_sandbox, env_sandbox):
        dependency_watcher.reset()
        sys.path.insert(0, str(sandbox.parent))

        yield

        sys.path.remove(str(sandbox.parent))


class WhatStringNotFound(Exception):
    pass


@dataclass
class Module:
    path_in: str
    source: str
    device: Optional[Any] = None
    path: Path = field(init=False)
    initial_state: bytes = field(init=False)

    def __post_init__(self) -> None:
        self.path = Path(self.path_in).absolute()
        self._fixed_source = dedent(self.source)
        self.write()

    def rewrite(self, new_source: str) -> None:
        self._fixed_source = dedent(new_source)
        self.write()

    def append(self, source: str) -> None:
        self._fixed_source += dedent(source)
        self.write()

    def prepend(self, source: str) -> None:
        self._fixed_source = dedent(source) + self._fixed_source
        self.write()

    def write(self):
        self.path.write_text(self._fixed_source)

    def replace(self, what: str, to: str) -> None:
        if what not in self.source:
            raise WhatStringNotFound()

        self._fixed_source = self._fixed_source.replace(what, to)
        self.write()

    def delete(self, what: str) -> None:
        self.replace(what, "")

    @property
    def name(self) -> str:
        if self.path.stem != "__init__":
            name = self.path.stem
        else:
            name = self.path.parent.absolute().stem

        return name

    def load(self) -> None:
        self.device = load_module(self.name)
        self.set_initial_state()

    def set_initial_state(self) -> None:
        self.initial_state = dill.dumps(self.device)

    def load_from(self, module: "Module"):
        self.device = getattr(module.device, self.name)
        self.set_initial_state()

    def assert_obj_in(self, obj_name: str) -> None:
        assert obj_name in self.device.__dict__

    def assert_obj_not_in(self, obj_name: str) -> None:
        assert obj_name not in self.device.__dict__

    def assert_not_changed(self) -> None:
        assert dill.dumps(self.device) == self.initial_state


@dataclass
class Reloader:
    root: Path
    device: smartreload.PartialReloader = field(init=False, default=None)

    def __post_init__(self):
        self.device = smartreload.PartialReloader(self.root, logger)

    def reload(self, module: Module) -> None:
        self.device.reload(module.path)

    def rollback(self) -> None:
        self.device.rollback()

    def assert_actions(self, *actions: str, ignore_order: bool = False) -> None:
        actions_str = tuple(repr(a) for a in self.device.applied_actions)
        if not ignore_order:
            assert actions_str == actions
        else:
            assert sorted(actions_str) == sorted(actions)
