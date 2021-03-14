import os
import signal
import stat
from time import sleep

from pytest import mark
from flaky import flaky
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

        smartreloader.remote().assert_applied_actions('Update Module: cakeshop', 'Add Import: cakeshop.cake', 'Update Function: cakeshop.print_cake')
        smartreloader.remote().resume()

        e.output("\ncheesecake").eval()

        smartreloader.exit()

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
