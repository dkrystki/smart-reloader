import json
import os
import shutil
import signal
import datetime as dt
import stat
from pathlib import Path
from textwrap import dedent
from time import sleep

from freezegun import freeze_time
from pytest import mark
from flaky import flaky

from smartreloader import sr_logger, e2e
from smartreloader.sr_logger import DEFAULT_LOGS_DIRECTORY
from tests import utils
from tests.utils import Module, Config


@mark.run(order=-1)
class TestClasses(utils.TestBase):
    @mark.parametrize(
        "command",
        ["python carwash.py", "python -m carwash", "./carwash.py", "carwash.py"],
    )
    @flaky(max_runs=3, min_passes=1)
    def test_basic(self, sandbox, smartreloader, command):
        config = Config()

        carwash = Module(
            "carwash.py",
            r"""
        from smartreloader import e2e
        
        car_colour = "red"
        
        if __name__ == "__main__":
            print(f"Cleaning {car_colour} car")
            e2e.Debugger.pause()
            print(f"Cleaning {car_colour} car")
            e2e.Debugger.pause()
            print(f"Cleaning {car_colour} car")
        """,
        )
        os.environ["PATH"] = f'{str(sandbox.absolute())}:{os.environ["PATH"]}'

        module_name = "__smartreloader_entrypoint__"

        if "-m" in command:
            module_name = "carwash"

        carwash.path.chmod(carwash.path.stat().st_mode | stat.S_IEXEC)

        e = smartreloader.start(command)
        e.output(r"Cleaning red car").eval()
        smartreloader.remote().wait_until_paused()
        carwash.replace('car_colour = "red"', 'car_colour = "green"')
        smartreloader.remote().assert_applied_actions(f'Update Module: {module_name}',
                                                      f'Update Variable: {module_name}.car_colour')
        smartreloader.remote().resume()
        e.output(r"\nCleaning green car").eval()

        smartreloader.remote().wait_until_paused()
        smartreloader.remote().reset()
        carwash.replace('car_colour = "green"', 'car_colour = "blue"')
        smartreloader.remote().assert_applied_actions(f'Update Module: {module_name}',
                                                      f'Update Variable: {module_name}.car_colour')
        smartreloader.remote().resume()
        e.output(r"\nCleaning blue car").eval()

        smartreloader.exit()

    @flaky(max_runs=3, min_passes=1)
    def test_full_reload(self, sandbox, smartreloader):
        config = Config()

        cakeshop = Module(
            "cakeshop.py",
            r"""
        from smartreloader import e2e
        
        class SuperType(int):
            pass

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
        """,
        )
        e = smartreloader.start("python cakeshop.py")
        e.output(r"Starting...").eval()

        smartreloader.remote().wait_until_paused()
        cakeshop.replace('class SuperType(int):', 'class SuperType(str):')

        e.output(r"\nStarting...").eval()

        cakeshop.replace('class SuperType(str):', 'class SuperType(float):')

        e.output(r"\nStarting...").eval()

        smartreloader.exit()

    def test_exits_on_sigint(self, sandbox, smartreloader):
        config = Config()

        cakeshop = Module(
            "cakeshop.py",
            r"""
        from smartreloader import e2e

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
        """,
        )
        e = smartreloader.start("python cakeshop.py")
        e.output(r"Starting...").eval()

        smartreloader.remote().wait_until_paused()
        smartreloader.send_signal(signal.SIGINT)
        e.exit(0).eval()

    def test_multiple_files_at_once(self, sandbox, smartreloader):
        config = Config()

        cakeshop = Module(
            "cakeshop.py",
            r"""
        from smartreloader import e2e
        import cake 

        name = "my cakeshop"

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
        """,
        )

        cake = Module(
            "cake.py",
            r"""
        name = "cheesecake"
        """,
        )

        e = smartreloader.start("python cakeshop.py")
        e.output(r"Starting...").eval()

        smartreloader.remote().wait_until_paused()
        cakeshop.replace('name = "my cakeshop"', 'name = "cool cakeshop"')
        cake.replace('name = "cheesecake"', 'name = "cool cakeshop"')

        e.output(r"\nStarting...").eval()

        smartreloader.exit()

    @flaky(max_runs=3, min_passes=1)
    def test_new_file(self, sandbox, smartreloader):
        config = Config()

        cakeshop = Module(
            "cakeshop.py",
            r"""
        from smartreloader import e2e
        
        def print_cake():
            print("no cake :(")

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
            print_cake()
        """,
        )

        e = smartreloader.start("python cakeshop.py")
        e.output(r"Starting...").eval()
        smartreloader.remote().wait_until_paused()

        cake = Module(
            "cake.py",
            r"""
        name = "cheesecake"
        """,
        )

        # so it doesn't trigger full reload on multiple events at once
        sleep(0.5)

        cakeshop.rewrite(r"""
        from smartreloader import e2e
        import cake
        
        def print_cake():
            print(cake.name)

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
            print_cake()
        """)

        smartreloader.remote().assert_applied_actions('Update Module: cakeshop', 'Add Import: cakeshop.cake',
                                                      'Update Function: cakeshop.print_cake')
        smartreloader.remote().resume()

        e.output("\ncheesecake").eval()

        smartreloader.exit()

    @flaky(max_runs=3, min_passes=1)
    def test_delete_file(self, sandbox, smartreloader):
        config = Config()

        cakeshop = Module(
            "cakeshop.py",
            r"""
        from smartreloader import e2e

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
        """,
        )

        cake = Module(
            "cake.py",
            r"""
        name = "cheesecake"
        """,
        )

        e = smartreloader.start("python cakeshop.py")
        e.output(r"Starting...").eval()
        smartreloader.remote().wait_until_paused()

        cake.path.unlink()
        e.output("\nStarting...").eval()
        smartreloader.exit()

    def test_logger(self, sandbox, smartreloader):
        log_dir = Path(sr_logger.DEFAULT_LOGS_DIRECTORY) / "sandbox" / sr_logger.SRLogger.datetime_to_folder_name(
            e2e.now)
        shutil.rmtree(str(log_dir), ignore_errors=True)

        config = Config()

        cakeshop = Module(
            "cakeshop.py",
            r"""
        from smartreloader import e2e
        import cake

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
        """,
        )

        cake = Module(
            "cake.py",
            r"""
        name = "cheesecake"
        """,
        )

        e = smartreloader.start("python cakeshop.py")
        e.output(r"Starting...").eval()
        smartreloader.remote().wait_until_paused()

        assert log_dir.exists()

        cake.rewrite('name = "black forest cake"')

        smartreloader.remote().freeze_time(dt.datetime(2025, 1, 1, 13, 0, 0))

        sleep(1.0)
        smartreloader.remote().freeze_time(dt.datetime(2025, 1, 1, 14, 0, 0))
        cake.rewrite('name = "birthday cake"')

        sleep(1.0)

        log_file = log_dir / sr_logger.LOG_FILE_NAME
        content = json.loads(log_file.read_text())

        content[0]["msg"] = "Create msg"

        assert content == [
            {
                'event_type': 'LogMsg',
                'msg': "Create msg",
                'time': '01/01/2025 12:00:00'
            },
            {
                'event_type': 'ModifiedEvent',
                'snapshot': '0_cake.py',
                'time': '01/01/2025 12:00:00'
            },
            {
                'event_type': 'LogMsg',
                'msg': 'Update Module: cake',
                'time': '01/01/2025 12:00:00'
            },
            {
                'event_type': 'LogMsg',
                'msg': 'Update Variable: cake.name',
                'time': '01/01/2025 12:00:00'
            },
            {
                'actions': ['Update Module: cake', 'Update Variable: cake.name'],
                'event_type': 'HotReloadedEvent',
                'objects': ['cake.name: Variable'],
                'time': '01/01/2025 12:00:00'
            }
        ]

    def test_error(self, sandbox, smartreloader):
        log_dir = Path(sr_logger.DEFAULT_LOGS_DIRECTORY) / "sandbox" / sr_logger.SRLogger.datetime_to_folder_name(
            e2e.now)
        shutil.rmtree(str(log_dir), ignore_errors=True)

        config = Config()

        cakeshop = Module(
            "cakeshop.py",
            r"""
        from smartreloader import e2e

        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
        """
        )

        e = smartreloader.start("python cakeshop.py")
        e.output(r"Starting...").eval()
        smartreloader.remote().wait_until_paused()

        cakeshop.rewrite(r"""
        from smartreloader import e2e
        
        value = 1/0
        
        if __name__ == "__main__":
            print(f"Starting...")
            e2e.Debugger.pause()
        """)

        e.output(dedent(r"""
                Traceback \(most recent call last\):
                  File ".*cakeshop\.py", line 4, in <module>
                    value = 1/0
                ZeroDivisionError: division by zero""")).eval()

        smartreloader.exit()
