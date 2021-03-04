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

        # ["python carwash.py", "python -m carwash", "./carwash.py", "carwash.py"],
        ["python carwash.py"],
    )
    def test_basic(self, sandbox, smartreloader, command):
        config = Config(e2e=True)

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

        carwash.path.chmod(carwash.path.stat().st_mode | stat.S_IEXEC)

        e = smartreloader.start(command)
        e.output(r"Cleaning red car").eval()

        smartreloader.remote().wait_unit_paused()
        sleep(2)
        carwash.replace('car_colour = "red"', 'car_colour = "green"')
        sleep(2)
        applied_actions = smartreloader.remote().get_applied_actions()
        assert applied_actions == ['Update Module: __smartreloader_entrypoint__',
                                   'Update Variable: __smartreloader_entrypoint__.car_colour',
                                   'UpdateGlobals Frame: <module>:8']
        smartreloader.remote().resume()
        e.output(r"\nCleaning green car").eval()

        smartreloader.remote().wait_unit_paused()
        sleep(2)
        carwash.replace('car_colour = "green"', 'car_colour = "blue"')
        sleep(2)
        applied_actions = smartreloader.remote().get_applied_actions()
        assert applied_actions == ['Update Module: __smartreloader_entrypoint__',
                                     'Update Variable: __smartreloader_entrypoint__.car_colour',
                                     'UpdateGlobals Frame: <module>:10']
        smartreloader.remote().resume()
        e.output(r"\nCleaning blue car").eval()


        smartreloader.exit()
