import errno
import os
from logging import getLogger
from pathlib import Path
from typing import List, Callable

from dataclasses import dataclass
from globmatch import glob_match
from watchdog.events import FileSystemEventHandler, FileSystemEvent, EVENT_TYPE_MODIFIED
from watchdog.observers import Observer

from smartreload import Reloader
from smartreload.misc import is_linux


logger = getLogger(__name__)


class Watchdog(FileSystemEventHandler):
    @dataclass
    class Sets:
        include: List[str]
        exclude: List[str]
        root: Path
        name: str = "Anonymous"

    _watch_files = ["**/*.py"]
    _ignore_files = [r"**/.*", r"**/*~", r"**/__pycache__"]

    def __init__(self, se: Sets, on_event: Callable):
        self.include = [p.lstrip("./") for p in se.include]
        self.exclude = [p.lstrip("./") for p in se.exclude]
        self.root = se.root

        self.reloader = Reloader(root=self.root, logger=logger)

        super().__init__()
        self.se = se
        self.on_event = on_event

        # self.logger.debug("Starting Inotify")
        self.observer = Observer()
        self.observer.schedule(self, str(self.se.root), recursive=True)

    def on_any_event(self, event: FileSystemEvent):
        if event.event_type != EVENT_TYPE_MODIFIED:
            return

        self.reloader.reload(event.src_path)

    def flush(self) -> None:
        self.observer.event_queue.queue.clear()

    def match(self, path: str, include: List[str], exclude: List[str]) -> bool:
        return not glob_match(path, exclude) and glob_match(path, include)

    def walk_dirs(self, on_match: Callable) -> None:
        def walk(path: Path):
            for p in path.iterdir():
                if glob_match(path, self.exclude):
                    continue
                on_match(str(p).encode("utf-8"))
                if p.is_dir():
                    walk(p)

        walk(self.root)

    def start(self) -> None:
        # self.logger.debug("Starting observer")

        if is_linux():

            def _add_dir_watch(self2, path, recursive, mask):
                """
                Adds a watch (optionally recursively) for the given directory path
                to monitor events specified by the mask.

                :param path:
                    Path to monitor
                :param recursive:
                    ``True`` to monitor recursively.
                :param mask:
                    Event bit mask.
                """
                if not os.path.isdir(path):
                    raise OSError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), path)
                self2._add_watch(path, mask)
                if recursive:
                    self.walk_dirs(on_match=lambda p: self2._add_watch(p, mask))

            from watchdog.observers.inotify_c import Inotify

            Inotify._add_dir_watch = _add_dir_watch

        self.observer.start()
        # self.logger.debug("Observer started")

    def stop(self) -> None:
        self.observer.stop()

    def dispatch(self, event: FileSystemEvent):
        """Dispatches events to the appropriate methods.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`FileSystemEvent`
        """
        from watchdog.utils import has_attribute, unicode_paths

        paths = []
        if has_attribute(event, "dest_path"):
            paths.append(unicode_paths.decode(event.dest_path))
        if event.src_path:
            paths.append(unicode_paths.decode(event.src_path))

        if any(
            self.match(
                str(Path(p).relative_to(self.root)),
                include=self.include,
                exclude=self.exclude,
            )
            for p in paths
        ):
            super().dispatch(event)
