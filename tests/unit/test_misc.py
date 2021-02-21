import pytest

from tests import utils
from tests.utils import Module, Reloader


class TestMisc(utils.TestBase):
    def test_syntax_error(self, sandbox, capsys):
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

        with pytest.raises(SyntaxError):
            reloader.reload(module)

    def test_other_error(self, sandbox, capsys):
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
        glob_var = 4/0
        """
        )

        with pytest.raises(ZeroDivisionError):
            reloader.reload(module)

    @pytest.mark.run(order=1)
    def test_pandas_objs(self, sandbox, capsys):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        import pandas as pd
        df1 = pd.DataFrame.from_dict({"col1": [1,2,3], "col2": [1,2,3]})
        df2 = pd.DataFrame.from_dict({"col1": [1,2,3], "col2": [1,2,3]})
        """,
        )

        module.load()

        module.rewrite(
            """
        import pandas as pd
        df1 = pd.DataFrame.from_dict({"col1": [1,2,3], "col2": [1,2,3]})
        df2 = pd.DataFrame.from_dict({"col1": [4,5,6], "col2": [1,2,3]})
        """
        )

        reloader.reload(module)

        reloader.assert_actions('Update: Module: module',
                                 'Update: Variable: module.df2')