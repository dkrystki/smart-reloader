from pytest import raises

from tests import utils
from tests.utils import Module, Reloader
from smartreload import dependency_watcher


class TestModules(utils.TestBase):
    def test_import_relative(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave_module
        from . import module
        """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        slave_global_var = 2
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module import slave_global_var

        global_var = 2
        """,
        )

        init.load()
        slave_module.load_from(init)
        module.load_from(init)

        module.replace("global_var = 2", "global_var = 5")

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Update: Variable: sandbox.module.global_var",
        )

        assert module.device.global_var == 5

        reloader.rollback()
        module.assert_not_changed()
        init.assert_not_changed()
        slave_module.assert_not_changed()

    def test_added_import(self, sandbox):
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
            import math
            glob_var = 4
            """
        )

        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Add: Import: module.math")

        module.assert_obj_in("math")

        reloader.rollback()
        module.assert_not_changed()

    def test_removed_import(self, sandbox):
        """
        We don't wanna remove imports because how python handles nested imports.
        """
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
            import math
            glob_var = 4
            """,
        )
        module.load()

        module.rewrite(
            """
            glob_var = 4
            """
        )

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module",
        )

        module.assert_obj_in("math")
        reloader.rollback()
        module.assert_not_changed()

    def test_add_relative(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave
        from . import master            
        """,
        )

        slave = Module(
            "slave.py",
            """
        slave_global_var = 2
        """,
        )

        master = Module(
            "master.py",
            """
        global_var = 2
        """,
        )
        init.load()

        slave.load_from(init)
        master.load_from(init)

        master.assert_obj_not_in("slave")

        master.rewrite(
            """
        from . import slave
        global_var = 2
        """
        )

        reloader.reload(master)

        reloader.assert_actions(
            "Update: Module: sandbox.master", "Add: Import: sandbox.master.slave"
        )

        master.assert_obj_in("slave")

        reloader.rollback()
        init.assert_not_changed()
        slave.assert_not_changed()
        master.assert_not_changed()

    def test_error_rolls_back(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import module
        from . import slave_module
        """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        from .module import global_var
        slave_global_var = 6 / global_var
        """,
        )

        module = Module(
            "module.py",
            """
            global_var = 2
            """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.rewrite("global_var = 0")

        with raises(ZeroDivisionError):
            reloader.reload(module)

        reloader.rollback()

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Update: Variable: sandbox.module.global_var",
            "Update: Module: sandbox.slave_module",
        )

        assert module.device.global_var == 2
        assert slave_module.device.slave_global_var == 3

        reloader.rollback()
        init.assert_not_changed()
        slave_module.assert_not_changed()
        module.assert_not_changed()

    def test_not_reloading_other_modules_for_foreign_objs(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
                      from . import slave_module
                      from . import module
                      """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        from typing import Optional
        slave_var = 1
        """,
        )

        module = Module(
            "module.py",
            """
        master_var = 2
        """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.rewrite(
            """
        from typing import Optional
        master_var = 2
        """
        )
        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: sandbox.module", "Add: Variable: sandbox.module.Optional"
        )

        reloader.rollback()
        init.assert_not_changed()
        slave_module.assert_not_changed()
        module.assert_not_changed()

    def test_update__all__(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
                      from . import slave_module
                      from . import module
                      """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        __all__ = ["tesla_car_1"]
        tesla_car_1 = "Model S"
        tesla_car_2 = "Model 3"
        tesla_car_3 = "Model 3"
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module import *
        """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        slave_module.replace(
            '__all__ = ["tesla_car_1"]',
            '__all__ = ["tesla_car_1", "tesla_car_2", "tesla_car_3"]',
        )

        reloader.reload(slave_module)

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Update: Module: sandbox.slave_module",
            "Update: All: sandbox.slave_module.__all__",
            "Add: Variable: sandbox.module.tesla_car_2",
            "Add: Variable: sandbox.module.tesla_car_3",
            ignore_order=True,
        )

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        reloader.rollback()
        init.assert_not_changed()
        slave_module.assert_not_changed()
        module.assert_not_changed()

    def test_add__all__(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave_module
        from . import module
        """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        tesla_car_1 = "Model S"
        tesla_car_3 = "Model 3"
        tesla_car_2 = "Model X"
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module import *
        """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        slave_module.append('__all__ = ["tesla_car_1"]')

        reloader.reload(slave_module)

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Update: Module: sandbox.slave_module",
            "Add: All: sandbox.slave_module.__all__",
            "Delete: Variable: sandbox.module.tesla_car_2",
            "Delete: Variable: sandbox.module.tesla_car_3",
            ignore_order=True,
        )

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        reloader.rollback()
        slave_module.assert_not_changed()
        module.assert_not_changed()
        init.assert_not_changed()

    def test_delete__all__(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave_module
        from . import module
        """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        tesla_car_1 = "Model S"
        tesla_car_2 = "Model 3"
        tesla_car_3 = "Model 3"
        __all__ = ["tesla_car_1"]
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module import *
        """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        slave_module.replace('__all__ = ["tesla_car_1"]', "")

        reloader.reload(slave_module)

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Update: Module: sandbox.slave_module",
            "Delete: All: sandbox.slave_module.__all__",
            "Add: Variable: sandbox.module.tesla_car_2",
            "Add: Variable: sandbox.module.tesla_car_3",
            ignore_order=True,
        )

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        reloader.rollback()
        init.assert_not_changed()
        module.assert_not_changed()
        slave_module.assert_not_changed()

    def test_delete_star_import(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave_module
        from . import module
        """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        __all__ = ["tesla_car_1"]
        tesla_car_1 = "Model S"
        tesla_car_2 = "Model 3"
        tesla_car_3 = "Model 3"
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module import *
        """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        module.rewrite("")

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: sandbox.module",
            "Delete: Variable: sandbox.module.tesla_car_1",
        )

        module.assert_obj_not_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        reloader.rollback()
        init.assert_not_changed()
        slave_module.assert_not_changed()
        module.assert_not_changed()

    def test_star_import_add_obj(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave_module
        from . import module
        """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        tesla_car_1 = "Model S"
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module import *
        """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")

        slave_module.append('tesla_car_2 = "Model S"')

        reloader.reload(slave_module)

        reloader.assert_actions(
            "Update: Module: sandbox.slave_module",
            "Add: Variable: sandbox.slave_module.tesla_car_2",
            "Update: Module: sandbox.module",
            "Add: Variable: sandbox.module.tesla_car_2",
        )

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")

        reloader.rollback()
        init.assert_not_changed()
        slave_module.assert_not_changed()
        module.assert_not_changed()

    def test_added_object_not_in_all(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave_module
        from . import module
        """,
        )

        slave_module = Module(
            "slave_module.py",
            """
        __all__ = ["tesla_car_1"]
        tesla_car_1 = "Model S"
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module import *
        """,
        )
        init.load()

        slave_module.load_from(init)
        module.load_from(init)

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")

        slave_module.append('tesla_car_2 = "Model 3"')

        reloader.reload(slave_module)

        reloader.assert_actions('Update: Module: sandbox.slave_module',
                                'Add: Variable: sandbox.slave_module.tesla_car_2')

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")

        reloader.rollback()
        init.assert_not_changed()
        slave_module.assert_not_changed()
        module.assert_not_changed()

    def test_not_reloading_on_removed_star_import(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import module
        """,
        )

        slave_module_1 = Module(
            "slave_module_1.py",
            """
        car_1 = "Model S"
        """,
        )
        slave_module_2 = Module(
            "slave_module_2.py",
            """
        car_2 = "Model 3"
        """,
        )

        module = Module(
            "module.py",
            """
        from .slave_module_1 import *
        from .slave_module_2 import *
        """,
        )
        init.load()

        slave_module_1.load_from(init)
        slave_module_2.load_from(init)
        module.load_from(init)

        module.assert_obj_in("car_1")
        module.assert_obj_in("car_2")

        module.replace("from .slave_module_2 import *", "")
        reloader.reload(module)
        reloader.assert_actions('Update: Module: sandbox.module',
                                 'Delete: Variable: sandbox.module.car_2')
        module.assert_obj_in("car_1")
        module.assert_obj_not_in("car_2")

        slave_module_2.append("car_3 = 'Model X'")
        reloader.reload(slave_module_2)
        reloader.assert_actions('Update: Module: sandbox.slave_module_2',
                                 'Add: Variable: sandbox.slave_module_2.car_3')

        module.assert_obj_in("car_1")
        module.assert_obj_not_in("car_2")
        module.assert_obj_not_in("car_3")
