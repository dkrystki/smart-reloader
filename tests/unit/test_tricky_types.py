from pytest import raises

from smartreload import FullReloadNeeded
from tests import utils
from tests.utils import Module, Reloader


class TestTrickyTypes(utils.TestBase):
    def test_should_not_reload(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        from uuid import uuid4
    
        class Car:
            owner: str
            name: str

            def __init__(self, name: str) -> None:
                self.name = name
                self.owner = uuid4()
        
        tesla = Car("Tesla")
        bmw = Car("BMD")
        scoda = Car("Scoda")
        """,
        )

        module.load()

        module.replace("Scoda", "Skoda")

        reloader.device.tricky_types.wait_until_finished()

        reloader.reload(module)

        reloader.assert_actions('Update: Module: module',
                                'Update: Variable: module.scoda')
