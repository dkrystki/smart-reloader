import ctypes
import sys
from logging import Logger
from pathlib import Path
from types import FrameType, ModuleType

from dataclasses import field
from typing import (
    List,
    TYPE_CHECKING, Generator,
)

from dataclasses import dataclass

from smartreloader.objects.base_objects import BaseAction
from smartreloader import utils

if TYPE_CHECKING:
    from smartreloader import PartialReloader
    from smartreloader.objects import Module


@dataclass(repr=False)
class Frame:
    python_obj: FrameType
    module: "Module"
    reloader: "PartialReloader"

    @dataclass(repr=False)
    class UpdateGlobals(BaseAction):
        obj: "Frame"

        def __repr__(self) -> str:
            return f"UpdateGlobals {repr(self.obj)}"

        def execute(self) -> None:
            self.obj.python_obj.f_globals.clear()
            self.obj.python_obj.f_globals.update(self.obj.module.python_obj.__dict__)
            utils.apply_changes_to_frame(self.obj.python_obj)

    def get_actions_for_update(self) -> List[BaseAction]:
        if not self.module:
            return []

        ret = []

        if self.module.python_obj.__dict__ != self.python_obj.f_globals:
            ret.append(self.UpdateGlobals(reloader=self.reloader, obj=self))

        return ret

    def update(self) -> None:
        actions = self.get_actions_for_update()

        for a in actions:
            a.pre_execute()
            a.execute()

    def __repr__(self) -> str:
        return f"Frame: {self.python_obj.f_code.co_name}:{self.python_obj.f_lineno}"


@dataclass(repr=False)
class Stack:
    logger: Logger
    module_file: Path
    reloader: "PartialReloader"

    frames: List[Frame] = field(init=False, default_factory=list)
    module: "Module" = field(init=False)

    def __post_init__(self) -> None:
        self.module = sys.modules.user_modules[str(self.module_file)][0].module_obj
        self._collect_frames()

    def update(self) -> None:
        for f in self.frames:
            f.update()

    def _collect_frames(self) -> None:
        def iterate_frames(frame) -> Generator[FrameType, None, None]:
            current_frame = frame
            while current_frame:
                yield current_frame
                current_frame = current_frame.f_back

        for thread_id, frame in sys._current_frames().items():
            for f in iterate_frames(frame):
                frame_module_filename = f.f_code.co_filename

                if str(self.module_file) == frame_module_filename:
                    module = self.module
                else:
                    module = None

                frame = Frame(python_obj=f,
                              module=module,
                              reloader=self.reloader)
                self.frames.append(frame)

        pass
