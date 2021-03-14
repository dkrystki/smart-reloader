import errno
import logging
import os
import signal
import sys
import threading
from logging import getLogger
from pathlib import Path
from threading import Thread
from time import sleep
from typing import TYPE_CHECKING, Callable, List, Deque

import watchdog.observers.inotify_buffer
from dataclasses import dataclass
from globmatch import glob_match
from watchdog.events import FileSystemEvent, FileSystemEventHandler, EVENT_TYPE_MODIFIED, EVENT_TYPE_CREATED, EVENT_TYPE_DELETED, EVENT_TYPE_MOVED
from watchdog.observers import Observer

from smartreloader import PartialReloader, console, sr_logger
from smartreloader.sr_logger import SRLogger
from smartreloader.misc import is_linux
from smartreloader.exceptions import FullReloadNeeded
from smartreloader.config import BaseConfig

from collections import deque, defaultdict


if TYPE_CHECKING:
    ...


def int_signal_handler(sig, frame):
    os._exit(0)

signal.signal(signal.SIGINT, int_signal_handler)


class Watchdog(FileSystemEventHandler):
    @dataclass
    class Callbacks:
        on_modify: Callable
        on_new_file: Callable
        on_delete_file: Callable
        on_multiple_files_at_once: Callable
        on_moved_file: Callable

    _unprocessed_events: Deque[FileSystemEvent]
    _callbacks: Callbacks

    def __init__(self, root: Path, watched_paths: List[str], ignored_paths: List[str], callbacks: Callbacks):
        self.root = root
        self._watched_paths = watched_paths
        self._ignored_paths = ignored_paths

        super().__init__()

        self._callbacks = callbacks
        self._unprocessed_events = deque()

        self.observer = Observer()
        self.observer.setDaemon(True)
        self.observer.schedule(self, str(self.root), recursive=True)
        watchdog.observers.inotify_buffer.logger.setLevel("INFO")
        self.new_event = threading.Event()

        self.producer = threading.Thread(target=self.events_producer)
        self.producer.setDaemon(True)

    def on_any_event(self, event: FileSystemEvent):
        path = Path(event.src_path)

        if not self.matches(path):
            return

        self._unprocessed_events.append(event)
        self.new_event.set()

    def matches(self, path: Path) -> bool:
        return not glob_match(str(path), self._ignored_paths) and glob_match(
            str(path), self._watched_paths
        )

    def remove_duplicate_events(self) -> None:
        ret = deque()
        file_to_events = defaultdict(list)

        type_events_order = [EVENT_TYPE_CREATED, EVENT_TYPE_DELETED, EVENT_TYPE_MOVED, EVENT_TYPE_MODIFIED]

        for e in self._unprocessed_events:
            file_to_events[e.src_path].append(e)

        for k in file_to_events.keys():
            events = file_to_events[k]
            events.sort(key=lambda x: type_events_order.index(x.event_type))
            ret.append(events[0])

        self._unprocessed_events = ret

    def events_producer(self) -> None:
        while True:
            self.new_event.wait()
            # wait a bit for more events
            sleep(0.05)

            self.remove_duplicate_events()

            if len(self._unprocessed_events) > 1:
                self._callbacks.on_multiple_files_at_once()

            event = self._unprocessed_events.pop()
            if event.event_type == EVENT_TYPE_MODIFIED:
                self._callbacks.on_modify(event)
            elif event.event_type == EVENT_TYPE_DELETED:
                self._callbacks.on_delete_file(event)
            elif event.event_type == EVENT_TYPE_CREATED:
                self._callbacks.on_new_file(event)
            elif event.event_type == EVENT_TYPE_MOVED:
                self._callbacks.on_moved_file(event)

            self.new_event.clear()

            if not self.observer.is_alive():
                return

    def flush(self) -> None:
        self.observer.event_queue.queue.clear()
        self._unprocessed_events.clear()

    def start(self) -> None:
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
        self.producer.start()

    def walk_dirs(self, on_match: Callable) -> None:
        def walk(path: Path):
            for p in path.iterdir():
                if glob_match(path, self._ignored_paths):
                    continue
                on_match(str(p).encode("utf-8"))
                if p.is_dir():
                    walk(p)

        walk(self.root)

    def stop(self, *args, **kwargs) -> None:
        self.observer.stop()

    def dispatch(self, event: FileSystemEvent):
        """Dispatches events to the appropriate methods.

        :param event:
            The event object representing the file system event.
        :type event:
            :class:`FileSystemEvent`
        """

        if event.event_type not in (EVENT_TYPE_MODIFIED, EVENT_TYPE_DELETED, EVENT_TYPE_MOVED, EVENT_TYPE_CREATED):
            return

        if self.matches(Path(event.src_path).relative_to(self.root)):
            super().dispatch(event)


class Reloader:
    root: Path
    config: BaseConfig
    partial_reloader: PartialReloader
    watchdog: Watchdog
    logger: SRLogger

    def __init__(self, root: str, config: BaseConfig):
        self.root = Path(root)

        self.logger = SRLogger(source_root=self.root)

        self.config = config
        self.partial_reloader = PartialReloader(root=self.root, logger=self.logger, config=self.config)
        signal.signal(signal.SIGUSR1, self._execute_full_reload)

        callbacks = Watchdog.Callbacks(on_modify=self.on_modify, on_new_file=self.on_new_file,
                                       on_delete_file=self.trigger_full_reload, on_multiple_files_at_once=self.trigger_full_reload,
                                       on_moved_file=self.trigger_full_reload)

        self.watchdog = Watchdog(self.root, watched_paths=self.config.watched_paths,
                                 ignored_paths=self.config.ignored_paths,
                                 callbacks=callbacks)

    def _on_multiple_files_at_once(self) -> None:
        self.trigger_full_reload()

    def _execute_full_reload(*args, **kwargs):
        sys.exit(3)

    def trigger_full_reload(self, *args, **kwargs) -> None:
        self.watchdog.stop()
        self.logger.info("Triggering full reload...")
        os.kill(os.getpid(), signal.SIGUSR1)

    def on_new_file(self, event: FileSystemEvent) -> None:
        pass

    def on_modify(self, event: FileSystemEvent):
        path = Path(event.src_path)
        self.logger.info(f"File {str(path)} modified, hot reloading...")

        try:
            self.config.before_reload(path)
            self.partial_reloader.reload(path)
            self.config.after_reload(path, self.partial_reloader.applied_actions)

            self.logger.log_hot_reloaded_event(actions=self.partial_reloader.applied_actions.copy(),
                                               objects=sys.modules.user_modules[str(path)][0].flat)
        except FullReloadNeeded:
            self.config.before_full_reload(path)
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

    def start(self) -> None:
        self.config.on_start(sys.argv)
        self.watchdog.start()
