import json
import os
import shutil
import logging
from logging import Logger
from pathlib import Path
from typing import Dict, Any, Optional, List, ClassVar, Type

from dataclasses import dataclass, field
import datetime as dt

from smartreloader import e2e
from smartreloader.objects import BaseAction, Object

DEFAULT_LOGS_DIRECTORY = Path.home() / ".smart-reloader/logs"
SOURCE_CHANGES_DIR_NAME = "source_changes"
LOG_FILE_NAME = "log.json"


@dataclass
class Event:
    sr_logger: "SRLogger"
    time: dt.datetime

    def to_dict(self) -> Dict[str, Any]:
        ret = {"time": self.time.strftime('%m/%d/%Y %H:%M:%S'), "event_type": type(self).__name__}
        return ret

    def write(self) -> None:
        content = json.dumps(self.to_dict(),
                             indent=4)

        with open(str(self.sr_logger.log_file), "a+") as f:
            if len(self.sr_logger.events) == 1:
                f.seek(f.tell() - 1, os.SEEK_SET)
                f.truncate()
            else:
                f.seek(f.tell() - 2, os.SEEK_SET)
                f.truncate()
                f.write(",\n")

            f.write(content)
            f.write("\n]\n")

@dataclass
class LogMsg(Event):
    level: int
    msg: str

    def to_dict(self) -> Dict[str, Any]:
        ret = super().to_dict()
        ret["msg"] = self.msg
        return ret


@dataclass
class HotReloadedEvent(Event):
    actions: List[BaseAction]
    objects: Dict[str, Object]

    def to_dict(self) -> Dict[str, Any]:
        ret = super().to_dict()
        ret["objects"] = tuple(f"{k}: {v.get_obj_type_name()}" for k, v in self.objects.items())
        ret["actions"] = [repr(a) for a in self.actions]
        return ret


@dataclass
class ModifiedEvent(Event):
    file: Path

    snapshot_filename: str = field(init=False)
    counter: ClassVar[int] = 0

    def __post_init__(self) -> None:
        self.snapshot_filename = f"{ModifiedEvent.counter}_{self.file.name}"
        shutil.copy(self.file, self.sr_logger.source_changes_dir / self.snapshot_filename)
        ModifiedEvent.counter += 1

    def to_dict(self) -> Dict[str, Any]:
        ret = super().to_dict()
        ret["snapshot"] = self.snapshot_filename
        return ret


@dataclass
class DeletedEvent(Event):
    ...


@dataclass
class CreatedEvent(Event):
    ...



@dataclass
class SRLogger:
    source_root: Path
    logs_directory: Path = DEFAULT_LOGS_DIRECTORY
    log_source_changes: bool = True

    log_directory: Path = field(init=False)
    events: List[Event] = field(init=False, default_factory=list)
    logger: ClassVar[Logger] = logging.getLogger("smart-reloader")
    log_file: Path = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        os.makedirs(str(self.logs_directory), exist_ok=True)

        self.log_directory = self.logs_directory / self.source_root.name / self.datetime_to_folder_name(dt.datetime.now())
        os.makedirs(str(self.log_directory), exist_ok=True)

        self.source_changes_dir = self.log_directory / SOURCE_CHANGES_DIR_NAME
        os.makedirs(str(self.source_changes_dir), exist_ok=True)

        self.initial_source_dir = self.log_directory / "initial_source"

        if self.initial_source_dir.exists():
            shutil.rmtree(str(self.initial_source_dir))

        shutil.copytree(self.source_root, self.initial_source_dir, )

        self.logger.setLevel(logging.INFO)
        self.log_file = self.log_directory / LOG_FILE_NAME
        self.log_file.touch()
        self.log_file.write_text("[\n]")

    @classmethod
    def datetime_to_folder_name(cls, date_time: dt.datetime) -> str:
        ret = date_time.strftime("%m_%d_%Y_%H:%M:%S")
        return ret

    def log_modified(self, file: Path) -> None:
        event = ModifiedEvent(time=dt.datetime.now(),
                            sr_logger=self,
                            file=file)
        self.add_event(event)

    def add_event(self, event: Event) -> None:
        self.events.append(event)
        event.write()

    def log_hot_reloaded_event(self, actions: List[BaseAction], objects: Dict[str, Object]) -> None:
        event = HotReloadedEvent(time=dt.datetime.now(),
                               sr_logger=self,
                               actions=actions,
                               objects=objects)

        self.add_event(event)

    def log(self, level: int, msg: str) -> None:
        event = LogMsg(sr_logger=self, level=level, time=dt.datetime.now(), msg=msg)

        self.add_event(event)
        self.logger.log(level, msg)

    def debug(self, msg: str) -> None:
        self.log(level=logging.DEBUG, msg=msg)

    def info(self, msg: str) -> None:
        self.log(level=logging.INFO, msg=msg)

    def warning(self, msg: str) -> None:
        self.log(level=logging.WARNING, msg=msg)
