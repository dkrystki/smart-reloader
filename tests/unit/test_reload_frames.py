from threading import Thread
from time import sleep

from tests import utils
from tests.utils import Module, Reloader


class TestReloadFrames(utils.TestBase):
    def test_wip(self, sandbox):
        module = Module("module.py",
        """
        from time import sleep
        glob_var = 1
        
        def start():
            elements = []
            for i in range(4):
                elements.append(glob_var)
                sleep(1)
            return elements
        """
        )
        module.load()

        reloader = Reloader(sandbox)

        def reload():
            sleep(1)
            module.replace("glob_var = 1", "glob_var = 5")

            reloader.reload(module)

        Thread(target=reload).start()
        ret = module.device.start()

        reloader.assert_actions(
            'Update: Module: module', 'Update: Variable: module.glob_var'
        )

        assert ret == [1, 1, 5, 5]
