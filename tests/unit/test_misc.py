import pytest

from tests import utils
from tests.utils import Module, Reloader


class TestMisc(utils.TestBase):
    def test_syntax_error(self, sandbox, capsys):
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

        reloader.reload(module)

        assert "SyntaxError: invalid syntax" in capsys.readouterr().out

    def test_other_error(self, sandbox, capsys):
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

        reloader.reload(module)

        assert "ZeroDivisionError" in capsys.readouterr().out
