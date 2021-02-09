from tests import utils
from tests.utils import Module, Reloader


class TestModules(utils.TestBase):
    def test_import_relative(self, sandbox):
        reloader = Reloader(sandbox.parent)

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

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Update: Variable: sandbox.module.global_var"
        )

        assert module.device.global_var == 5

    def test_added_import(self, sandbox):
        reloader = Reloader(sandbox)

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

        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Add: Import: module.math")

        module.assert_obj_in("math")

    def test_removed_import(self, sandbox):
        """
        We don't wanna remove imports because how python handles nested imports.
        """
        reloader = Reloader(sandbox)

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

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module"
        )

        module.assert_obj_in("math")

    def test_add_relative(self, sandbox):
        reloader = Reloader(sandbox.parent)

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

        reloader.reload(master)

        reloader.assert_actions('Update: Module: sandbox.master', 'Add: Import: sandbox.master.slave')

        master.assert_obj_in("slave")

    def test_error_rolls_back(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module("__init__.py",
                      """
                      from . import module
                      from . import slave_module
                      """
                      )

        slave_module = Module("slave_module.py",
                              """
                              from .module import global_var
                              slave_global_var = 6 / global_var
                              """
                              )

        module = Module("module.py",
                        """
                        global_var = 2
                        """
                        )
        init.load()

        slave_module.device = init.device.slave_module
        module.device = init.device.module

        module.rewrite("global_var = 0")

        reloader.reload(module)

        reloader.assert_actions('Update: Module: sandbox.module',
                                'Update: Variable: sandbox.module.global_var',
                                'Update: Module: sandbox.slave_module',
                                'Rollback: Update: Module: sandbox.slave_module',
                                'Rollback: Update: Variable: sandbox.module.global_var',
                                'Rollback: Update: Module: sandbox.module')

        assert module.device.global_var == 2
        assert slave_module.device.slave_global_var == 3

    def test_not_reloading_other_modules_for_foreign_objs(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module("__init__.py",
                      """
                      from . import slave_module
                      from . import module
                      """
                      )

        slave_module = Module("slave_module.py",
        """
        from typing import Optional
        slave_var = 1
        """
        )

        module = Module("module.py",
        """
        master_var = 2
        """
        )
        init.load()

        slave_module.device = init.device.slave_module
        module.device = init.device.module

        module.rewrite("""
        from typing import Optional
        master_var = 2
        """
        )
        reloader.reload(module)

        reloader.assert_actions('Update: Module: sandbox.module', 'Add: Variable: sandbox.module.Optional')

    def test_update__all__(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module("__init__.py",
                      """
                      from . import slave_module
                      from . import module
                      """
                      )

        slave_module = Module("slave_module.py",
                              """
                              __all__ = ["tesla_car_1"]
                              tesla_car_1 = "Model S"
                              tesla_car_2 = "Model 3"
                              tesla_car_3 = "Model 3"
                              """
                              )

        module = Module("module.py",
                        """
                        from .slave_module import *
                        """
                        )
        init.load()

        slave_module.device = init.device.slave_module
        module.device = init.device.module

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        slave_module.replace('__all__ = ["tesla_car_1"]', '__all__ = ["tesla_car_1", "tesla_car_2", "tesla_car_3"]')

        reloader.reload(slave_module)

        reloader.assert_actions('Update: Module: sandbox.slave_module',
                                 'Update: All: sandbox.slave_module.__all__',
                                 'Update: Module: sandbox.module',
                                 'Add: Variable: sandbox.module.tesla_car_2',
                                'Add: Variable: sandbox.module.tesla_car_3', ignore_order=True)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

    def test_add__all__(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module("__init__.py",
                      """
                      from . import slave_module
                      from . import module
                      """
                      )

        slave_module = Module("slave_module.py",
                              """
                              tesla_car_1 = "Model S"
                              tesla_car_2 = "Model 3"
                              tesla_car_3 = "Model 3"
                              """
                              )

        module = Module("module.py",
                        """
                        from .slave_module import *
                        """
                        )
        init.load()

        slave_module.device = init.device.slave_module
        module.device = init.device.module

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        slave_module.append('__all__ = ["tesla_car_1"]')

        reloader.reload(slave_module)

        reloader.assert_actions('Update: Module: sandbox.slave_module',
                                     'Add: All: sandbox.slave_module.__all__',
                                     'Update: Module: sandbox.module',
                                     'Delete: Variable: sandbox.module.tesla_car_2',
                                     'Delete: Variable: sandbox.module.tesla_car_3', ignore_order=True)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

    def test_delete__all__(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module("__init__.py",
                      """
                      from . import slave_module
                      from . import module
                      """
                      )

        slave_module = Module("slave_module.py",
                              """
                              __all__ = ["tesla_car_1"]
                              tesla_car_1 = "Model S"
                              tesla_car_2 = "Model 3"
                              tesla_car_3 = "Model 3"
                              """
                              )

        module = Module("module.py",
                        """
                        from .slave_module import *
                        """
                        )
        init.load()

        slave_module.device = init.device.slave_module
        module.device = init.device.module

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        slave_module.replace('__all__ = ["tesla_car_1"]', "")

        reloader.reload(slave_module)

        reloader.assert_actions('Update: Module: sandbox.slave_module',
                                 'Delete: All: sandbox.slave_module.__all__',
                                 'Update: Module: sandbox.module',
                                 'Add: Variable: sandbox.module.tesla_car_2',
                                 'Add: Variable: sandbox.module.tesla_car_3', ignore_order=True)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

    def test_delete_star_import(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module("__init__.py",
                      """
                      from . import slave_module
                      from . import module
                      """
                      )

        slave_module = Module("slave_module.py",
                              """
                              __all__ = ["tesla_car_1"]
                              tesla_car_1 = "Model S"
                              tesla_car_2 = "Model 3"
                              tesla_car_3 = "Model 3"
                              """
                              )

        module = Module("module.py",
                        """
                        from .slave_module import *
                        """
                        )
        init.load()

        slave_module.device = init.device.slave_module
        module.device = init.device.module

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        module.rewrite("")

        reloader.reload(module)

        reloader.assert_actions('Update: Module: sandbox.module',
                                'Delete: Variable: sandbox.module.tesla_car_1')

        module.assert_obj_not_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")
