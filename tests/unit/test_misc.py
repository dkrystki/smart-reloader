import pytest

from tests import utils
from tests.utils import Module, Reloader


class TestMisc(utils.TestBase):
    def test_syntax_error(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module("module.py",
        """
        glob_var = 4
        """
        )

        module.load()

        module.rewrite(
        """
        glob_var = 4pfds
        """
        )

        with pytest.raises(SyntaxError):
            reloader.reload(module)

    def test_other_error(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module("module.py",
        """
        glob_var = 4
        """
        )

        module.load()

        module.rewrite(
        """
        glob_var = 4/0
        """
        )

        with pytest.raises(ZeroDivisionError):
            reloader.reload(module)
