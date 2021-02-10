import errno
import logging
import os
import sys
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List

import watchdog.observers.inotify_buffer
from globmatch import glob_match
from watchdog.events import EVENT_TYPE_MODIFIED, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from smartreload import PartialReloader, console
from smartreload.misc import is_linux
from smartreload.partialreloader import FullReloadNeeded

logger = getLogger("Reloader")
logger.setLevel(logging.INFO)


if TYPE_CHECKING:
    from smartreload.config import Config


class Reloader(FileSystemEventHandler):
    def __init__(self, root: str, config: "Config"):
        self.root = Path(root)
        self.partial_reloader = PartialReloader(root=self.root, logger=logger)

        self.config = config

        super().__init__()

        # self.logger.debug("Starting Inotify")
        self.observer = Observer()
        self.observer.schedule(self, str(self.root), recursive=True)
        watchdog.observers.inotify_buffer.logger.setLevel("INFO")

    def trigger_full_reload(self) -> None:
        sys.exit(0)

    def matches(self, path: Path) -> bool:
        return not glob_match(str(path), self.config.ignored_paths) and glob_match(
            str(path), self.config.watched_paths
        )

    def on_any_event(self, event: FileSystemEvent):
        path = Path(event.src_path)

        if not self.matches(path):
            return

        try:
            self.config.before_reload(path)
            self.partial_reloader.reload(path)
            self.config.after_reload(path, self.partial_reloader.applied_actions)
        except FullReloadNeeded:
            self.config.before_full_reload(path, None)
            self.trigger_full_reload()
        except Exception:
            from rich.traceback import Traceback

            self.config.after_rollback(path, self.partial_reloader.applied_actions)

            exc_type, exc_value, traceback = sys.exc_info()
            trace = Traceback.extract(exc_type, exc_value, traceback)
            trace.stacks[0].frames = trace.stacks[0].frames[-1:]
            trace.stacks = [trace.stacks[0]]
            traceback_obj = Traceback(trace=trace, width=800, show_locals=True)
            console.print(traceback_obj)

            self.partial_reloader.rollback()
            self.config.after_rollback(path, self.partial_reloader.applied_actions)

        self.flush()

    def flush(self) -> None:
        self.observer.event_queue.queue.clear()

    def walk_dirs(self, on_match: Callable) -> None:
        def walk(path: Path):
            for p in path.iterdir():
                if glob_match(path, self.config.ignored_paths):
                    continue
                on_match(str(p).encode("utf-8"))
                if p.is_dir():
                    walk(p)

        walk(self.root)

    def start(self) -> None:
        # self.logger.debug("Starting observer")

        self.config.on_start()

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
