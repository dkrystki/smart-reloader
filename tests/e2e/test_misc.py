from time import sleep

from pytest import mark

from tests import utils
from tests.utils import Module, Reloader


class TestClasses(utils.TestBase):
    @mark.parametrize("command", ["carwash.py", " -m carwash"])
    def test_basic(self, sandbox, smartreload, command):
        carwash = Module("carwash.py",
        r"""
        car_colour = "red"
        
        if __name__ == "__main__":
            print(f"Cleaning {car_colour} car")
            input()
            print(f"Cleaning {car_colour} car")
        """
        )

        e = smartreload.start("python " + command)
        e.output(r"Cleaning red car").eval()
        carwash.replace('car_colour = "red"', 'car_colour = "green"')
        sleep(0.2)
        smartreload.sendline("")

        e.output(r"Cleaning green car").eval()

        smartreload.exit()
