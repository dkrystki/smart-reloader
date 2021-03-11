import os
import re
import signal
import subprocess
from pathlib import Path
from subprocess import Popen
from threading import Thread
from time import sleep
from typing import Callable, List, Optional, Type, NewType

import pyte
from rhei import Stopwatch
from stickybeak import Injector

from smartreloader.e2e import STICKYBEAK_PORT

TIMEOUT = 4

Signal = NewType("Signal", int)

injector = Injector(address=f"http://localhost:{STICKYBEAK_PORT}", download_deps=False)


class AssertInTime:
    class TIMEOUT(Exception):
        pass

    def __init__(self, condition: Callable, timeout=TIMEOUT):
        self.condition = condition
        self.sw = Stopwatch()
        self.sw.start()

        while True:
            if condition():
                break

            if self.sw.value >= timeout:
                raise self.TIMEOUT(self)
            sleep(0.05)


class Expecter:
    def __init__(self, spawn: "SpawnShell") -> None:
        self._spawn = spawn
        self.expected: List[str] = []
        self._return_code = 0
        self._expect_exit = False

    def output(self, regex: str) -> "Expecter":
        self.expected.append(regex)
        return self

    def cmd(self, cmd: str) -> "Expecter":
        self.expected.append(re.escape(cmd) + r"\n")
        return self

    def raw(self, raw: str) -> "Expecter":
        self.expected.append(re.escape(raw))
        return self

    def exit(self, return_code=0) -> "Expecter":
        self._expect_exit = True
        self._return_code = return_code
        return self

    @property
    def expected_regex(self):
        return "".join(self.expected)

    def pop(self) -> None:
        self.expected.pop()

    def eval(self, timeout: int = TIMEOUT) -> None:
        def condition():
            return re.fullmatch(
                self.expected_regex, self._spawn.get_cleaned_display(), re.DOTALL
            )

        AssertInTime(condition, timeout)

        if self._expect_exit:
            self._spawn.stop_collecting = True

            # check if has exited
            def condition():
                return self._spawn.process.poll() == self._return_code

            try:
                AssertInTime(condition, timeout)
            except AssertInTime.TIMEOUT:
                raise AssertInTime.TIMEOUT(
                    f"Process has not exit on time with proper"
                    f" exit code (last exit code = {self._spawn.process.poll()})"
                )


class SmartReloader:
    process: Optional[Popen] = None

    @injector.klass
    class Remote:
        @classmethod
        def get_applied_actions(cls) -> List[str]:
            applied_actions = [str(a) for a in reloader.partial_reloader.applied_actions]
            return applied_actions

        @classmethod
        def reset(cls) -> None:
            reloader.partial_reloader.reset()

        @classmethod
        def assert_applied_actions(cls, *actions, timeout=2) -> None:
            from time import sleep

            passed_time = 0.0
            sleep_time = 0.01
            while True:
                sleep(sleep_time)
                passed_time += sleep_time

                applied_actions = tuple(str(a) for a in reloader.partial_reloader.applied_actions)
                if actions == applied_actions:
                    break

                if passed_time >= timeout:
                    raise AssertionError(f"{actions} != {applied_actions}")

                sleep(0.2)

        @classmethod
        def resume(cls) -> None:
            from smartreloader.e2e import Debugger
            Debugger.resume()

        @classmethod
        def kill_stickybeak(cls) -> None:
            from smartreloader import e2e
            from threading import Thread
            from time import sleep

            def thread():
                sleep(0.5)
                e2e.server.exit()

            Thread(target=thread).start()

        @classmethod
        def wait_until_paused(cls) -> None:
            from smartreloader.e2e import Debugger
            Debugger.wait_until_paused()

    def __init__(self):
        self.screen = pyte.Screen(200, 50)
        self.stream = pyte.ByteStream(self.screen)

    def start(self, command: str) -> Expecter:
        self.expecter = None
        self._buffer = []

        self.stop_collecting = False
        self.output_collector = Thread(target=self._output_collector)

        environ = os.environ.copy()
        environ["PYTHONUNBUFFERED"] = "True"
        environ["SMART_RELOADER_E2E_TEST"] = "True"

        # Add project root to python path so we can import test modules

        self.process = Popen(
            f"python -m smartreloader.entrypoint {command}".split(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            env=environ,
            preexec_fn=os.setsid,
        )

        self.output_collector.start()
        self.expecter = Expecter(self)

        injector.connect()
        return self.expecter

    def exit(self) -> None:
        self.print_info()

        if not self.process:
            return
        if self.process.poll() is not None:
            return

        self.force_kill()

    def force_kill(self):
        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)

    def remote(self) -> Type["SmartReloader.Remote"]:
        return SmartReloader.Remote

    def on_exit(self) -> None:
        self.exit()

    def send(self, text: str, expect=True) -> None:
        if expect:
            self.expecter.raw(text)
        self.process.stdin.write(text.encode("utf-8"))
        self.process.stdin.flush()

    def send_signal(self, sig: Signal) -> None:
        self.process.send_signal(sig)

    def sendline(self, line: str, expect=True) -> None:
        if expect:
            self.expecter.cmd(line)
        self.process.stdin.writelines([f"{line}\n".encode("utf-8")])
        self.process.stdin.flush()

    def _output_collector(self):
        try:
            while not self.stop_collecting:
                c: bytes = self.process.stdout.read(1)
                if not c:
                    return
                self._buffer.append(c)
                if c == b"\n":
                    c = b"\r\n"
                self.stream.feed(c)
        except OSError:
            pass

    def get_display(self):
        # Remove "Warning: Output is not a terminal"
        def ignore(s: str) -> bool:
            if "Warning: Output is not a terminal" in s:
                return True
            if "Warning: Input is not a terminal" in s:
                return True

            return False

        display_raw = self.screen.display
        display = [s for s in display_raw if not ignore(s)]
        return display

    def get_cleaned_display(self):
        return "\n".join([s.rstrip() for s in self.get_display() if s.rstrip()])

    def print_info(self):
        print("\nDisplay:")
        print(self.get_cleaned_display())
        expected_multiline = self.expecter.expected_regex.replace(r"\n", "\n")
        print(f"\nExpected (multiline):\n{expected_multiline}")
        print(f"\nExpected (raw):\n{self.expecter.expected_regex}")
