from tests import utils
from tests.utils import Module, Reloader


class TestModules(utils.TestBase):
    def test_import_relative(self, sandbox):
        init = Module("__init__.py",
        """
        from . import slave_module
        from . import module
        """
        )

        slave_module = Module("slave_module.py",
        """
        slave_global_var = 2

        def slave_fun(arg1: str, arg2: str) -> str:
            return "Slave test"
        """
        )

        module = Module("module.py",
        """
        from .slave_module import slave_global_var

        global_var = 2

        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """
        )
        init.load()

        slave_module.device = init.device.slave_module
        module.device = init.device.module

        module.replace("global_var = 2", "global_var = 5")

        reloader = Reloader(sandbox.parent)
        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Update: Variable: sandbox.module.global_var"
        )

        assert module.device.global_var == 5

    def test_added_import(self, sandbox):
        module = Module("module.py",
        """
        glob_var = 4
        """
        )

        module.load()

        assert not hasattr(module, "math")

        module.rewrite(
            """
            import math
            glob_var = 4
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Add: Import: module.math")

        module.assert_obj_in("math")

    def test_removed_import(self, sandbox):
        """
        We don't wanna remove imports because how python handles nested imports.
        """

        module = Module("module.py",
                """
            import math
            glob_var = 4
            """
        )
        module.load()

        module.assert_obj_in("math")

        module.rewrite(
                """
            glob_var = 4
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module"
        )

        module.assert_obj_in("math")

    def test_add_relative(self, sandbox):
        init = Module("__init__.py",
            """
        from . import slave
        from . import master            
        """
        )

        slave = Module("slave.py",
        """
        slave_global_var = 2
        """)

        master = Module("master.py",
        """
        global_var = 2
        """)
        init.load()

        slave.device = init.device.slave
        master.device = init.device.master

        master.assert_obj_not_in("slave_module")

        master.rewrite("""
        from . import slave
        global_var = 2
        """)

        reloader = Reloader(sandbox.parent)
        reloader.reload(master)

        reloader.assert_actions(
                'Update: Module: sandbox.master',
         'Add: Import: sandbox.master.slave',
         'Update: Module: sandbox'
                )

        master.assert_obj_in("slave")
