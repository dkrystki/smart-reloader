import pytest
from pytest import raises

from tests import utils
from tests.utils import Module, Reloader, Config
from smartreload import dependency_watcher


@pytest.mark.run(order=1)
class TestPlugins(utils.TestBase):
    def test_pandas_objs(self, sandbox, capsys):
        reloader = Reloader(sandbox, config=Config(plugins=["smart_pandas"]))

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

        reloader.assert_actions('Update Module: module', 'Update Pandas.Dataframe: module.df2')