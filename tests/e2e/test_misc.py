import os
import stat
from time import sleep

from pytest import mark

from tests import utils
from tests.utils import Module, Reloader


@mark.run(order=-1)
class TestClasses(utils.TestBase):
    @mark.parametrize(
        "command",
        ["python carwash.py", "python -m carwash", "./carwash.py", "carwash.py"],
    )
    def test_basic(self, sandbox, smartreload, command):
        carwash = Module(
            "carwash.py",
            r"""
        car_colour = "red"
        
        if __name__ == "__main__":
            print(f"Cleaning {car_colour} car")
            input()
            print(f"Cleaning {car_colour} car")
        """,
        )
        os.environ["PATH"] = f'{str(sandbox.absolute())}:{os.environ["PATH"]}'

        carwash.path.chmod(carwash.path.stat().st_mode | stat.S_IEXEC)

        e = smartreload.start(command)
        e.output(r"Cleaning red car").eval()
        carwash.replace('car_colour = "red"', 'car_colour = "green"')
        sleep(0.2)
        smartreload.sendline("")

        e.output(r"Cleaning green car").eval()

        smartreload.exit()
