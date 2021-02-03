import sys
import errno
import os
from logging import getLogger
import logging
from pathlib import Path
from typing import List, Callable

from globmatch import glob_match
from watchdog.events import FileSystemEventHandler, FileSystemEvent, EVENT_TYPE_MODIFIED
from watchdog.observers import Observer

from smartreload import PartialReloader, console
from smartreload.misc import is_linux
import watchdog.observers.inotify_buffer

logger = getLogger("Reloader")
logger.setLevel(logging.INFO)


class Reloader(FileSystemEventHandler):
    def __init__(self, root: str):
        self.root = Path(root)
        self.partial_reloader = PartialReloader(root=self.root, logger=logger)

        super().__init__()

        # self.logger.debug("Starting Inotify")
        self.observer = Observer()
        self.observer.schedule(self, str(self.root), recursive=True)
        watchdog.observers.inotify_buffer.logger.setLevel("INFO")

    @property
    def watch_files(self) -> List[str]:
        return ["**/*.py"]

    @property
    def ignore_files(self) -> List[str]:
        return [r"**/.*", r"**/*~", r"**/__pycache__"]

    @property
    def fully_reloadable_files(self) -> List[str]:
        return []

    def trigger_full_reload(self) -> None:
        sys.exit(0)

    def matches(self, path: Path) -> bool:
        return not glob_match(str(path), self.ignore_files) and glob_match(str(path), self.watch_files)

    def on_any_event(self, event: FileSystemEvent):
        path = Path(event.src_path)

        if not self.matches(path):
            return

        if glob_match(str(path), self.fully_reloadable_files):
            self.trigger_full_reload()

        try:
            self.partial_reloader.reload(path)
        except Exception as e:
            from rich.traceback import Traceback

            exc_type, exc_value, traceback = sys.exc_info()
            trace = Traceback.extract(exc_type, exc_value, traceback)
            trace.stacks[0].frames = trace.stacks[0].frames[-1:]
            trace.stacks = [trace.stacks[0]]
            traceback_obj = Traceback(
                trace=trace,
                width=800,
                show_locals=True
            )
            console.print(traceback_obj)

            # self.trigger_full_reload()

        self.flush()

    def flush(self) -> None:
        self.observer.event_queue.queue.clear()

    def walk_dirs(self, on_match: Callable) -> None:
        def walk(path: Path):
            for p in path.iterdir():
                if glob_match(path, self.ignore_files):
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

        if event.event_type != EVENT_TYPE_MODIFIED:
            return

        if self.matches(Path(event.src_path).relative_to(self.root)):
            super().dispatch(event)
