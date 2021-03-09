import os
import stat
from time import sleep

from pytest import mark

from tests import utils
from tests.utils import Module, Config


@mark.run(order=-1)
class TestClasses(utils.TestBase):
    @mark.parametrize(
        "command",

        ["python carwash.py", "python -m carwash", "./carwash.py", "carwash.py"],
    )
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
        sleep(2)
        carwash.replace('car_colour = "green"', 'car_colour = "blue"')
        smartreloader.remote().assert_applied_actions(f'Update Module: {module_name}',
                                                      f'Update Variable: {module_name}.car_colour')
        sleep(2)
        smartreloader.remote().resume()
        e.output(r"\nCleaning blue car").eval()

        smartreloader.exit()

    def test_full_reload(self, sandbox, smartreloader):
        config = Config()

        carwash = Module(
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
        carwash.replace('class SuperType(int):', 'class SuperType(str):')

        e.output(r"\nStarting...").eval()

        carwash.replace('class SuperType(str):', 'class SuperType(float):')

        e.output(r"\nStarting...").eval()

        smartreloader.exit()
