import pytest
from pytest import raises

from tests import utils
from tests.utils import Module, MockedPartialReloader, Config


@pytest.mark.run(order=1)
class TestPlugins(utils.TestBase):
    def test_pandas_objs(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox, config=Config(plugins=["smart_pandas"]))

        module = Module(
            "module.py",
            """
        import pandas as pd
        df1 = pd.DataFrame.from_dict({"col1": [1,2,3], "col2": [1,2,3]})
        df2 = pd.DataFrame.from_dict({"col1": [1,2,3], "col2": [1,2,3]})
        """,
        )

        module.load()
        reloader.assert_objects(module, 'module.pd: Import', 'module.df1: Dataframe', 'module.df2: Dataframe')

        module.rewrite(
            """
        import pandas as pd
        df1 = pd.DataFrame.from_dict({"col1": [1,2,3], "col2": [1,2,3]})
        df2 = pd.DataFrame.from_dict({"col1": [4,5,6], "col2": [1,2,3]})
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.pd: Import', 'module.df1: Dataframe', 'module.df2: Dataframe')

        reloader.assert_actions('Update Module: module', 'Update Pandas.Dataframe: module.df2')
