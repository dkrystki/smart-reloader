import pytest

from tests import utils
from tests.utils import Module, Reloader


class TestLists(utils.TestBase):
    def test_basic(self, sandbox, capsys):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        glob_var = 4
        """,
        )

        module.load()

        module.rewrite(
            """
        glob_var = 4pfds
        """
        )

        reloader.reload(module)
