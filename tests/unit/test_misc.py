import sys

import pytest

from tests import utils
from tests.utils import Module, MockedPartialReloader


class TestMisc(utils.TestBase):
    def test_syntax_error(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox)

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
        reloader = MockedPartialReloader(sandbox)

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

    def test_edited_not_imported_file(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox)

        cupcake = Module(
            "cupcake.py",
            """
        cupcakes_n = 100
        """,
        )

        cake_shop = Module(
            "cake_shop.py",
            """
        shop_open = True
        """,
        )

        cupcake.rewrite("cupcakes_n = 150")

        cake_shop.load()

        reloader.reload(cupcake)
        reloader.assert_actions()

    def test_imported_twice(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import cupcake
        import cupcake    
        """,
        )

        cupcake = Module(
            "cupcake.py",
            """
        cupcakes_n = 100
        """,
        )

        init.load()

        cupcake.rewrite("cupcakes_n = 150")
        reloader.reload(cupcake)
        reloader.assert_actions('Update Module: sandbox.cupcake',
                                'Update Variable: sandbox.cupcake.cupcakes_n',
                                'Update Module: cupcake',
                                'Update Variable: cupcake.cupcakes_n',
                                'Update Module: cupcake')

        assert sys.modules["sandbox.cupcake"].cupcakes_n == 150
        assert sys.modules["cupcake"].cupcakes_n == 150
        assert sys.modules["sandbox.cupcake"] is not sys.modules["cupcake"]

    def test_new_file(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import cupcake
        import cupcake    
        """,
        )

        cupcake = Module(
            "cupcake.py",
            """
        cupcakes_n = 100
        """,
        )

        init.load()

        cupcake.rewrite("cupcakes_n = 150")
        reloader.reload(cupcake)
        reloader.assert_actions('Update Module: sandbox.cupcake',
                                'Update Variable: sandbox.cupcake.cupcakes_n',
                                'Update Module: cupcake',
                                'Update Variable: cupcake.cupcakes_n',
                                'Update Module: cupcake')

        assert sys.modules["sandbox.cupcake"].cupcakes_n == 150
        assert sys.modules["cupcake"].cupcakes_n == 150
        assert sys.modules["sandbox.cupcake"] is not sys.modules["cupcake"]

    def test_delete_file(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import cupcake
        import cupcake    
        """,
        )

        cupcake = Module(
            "cupcake.py",
            """
        cupcakes_n = 100
        """,
        )

        init.load()

        cupcake.rewrite("cupcakes_n = 150")
        reloader.reload(cupcake)
        reloader.assert_actions('Update Module: sandbox.cupcake',
                                'Update Variable: sandbox.cupcake.cupcakes_n',
                                'Update Module: cupcake',
                                'Update Variable: cupcake.cupcakes_n',
                                'Update Module: cupcake')

        assert sys.modules["sandbox.cupcake"].cupcakes_n == 150
        assert sys.modules["cupcake"].cupcakes_n == 150
        assert sys.modules["sandbox.cupcake"] is not sys.modules["cupcake"]
