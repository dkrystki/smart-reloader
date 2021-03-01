from pytest import raises, mark

from tests import utils
from tests.utils import Module, Reloader


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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.slave_global_var: Variable')
            reloader.assert_objects(module, 'sandbox.module.global_var: Variable',
                                            'sandbox.module.slave_global_var: Foreigner')
            assert module.device.global_var == 2

        assert_not_reloaded()

        module.replace("global_var = 2", "global_var = 5")

        reloader.reload(module)
        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.slave_global_var: Variable')
        reloader.assert_objects(module, 'sandbox.module.global_var: Variable',
                                        'sandbox.module.slave_global_var: Foreigner')

        reloader.assert_actions(
            "Update Module: sandbox.module",
            "Update Variable: sandbox.module.global_var",
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

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.glob_var: Variable')
            module.assert_obj_not_in("math")
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
            import math
            glob_var = 4
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.glob_var: Variable', 'module.math: Import')

        reloader.assert_actions("Update Module: module", "Add Import: module.math")

        module.assert_obj_in("math")

        reloader.rollback()
        assert_not_reloaded()

    def test_removed_import(self, sandbox):
        """
        We don't wanna remove imports because how python handles nested imports.
        """
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
            import math
            """,
        )
        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.math: Import')
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite("")

        reloader.reload(module)
        reloader.assert_objects(module)

        reloader.assert_actions("Update Module: module")

        module.assert_obj_in("math")
        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.master: Import', 'sandbox.slave: Import')
            reloader.assert_objects(slave, 'sandbox.slave.slave_global_var: Variable')
            reloader.assert_objects(master, 'sandbox.master.global_var: Variable')
            init.assert_not_changed()
            slave.assert_not_changed()
            master.assert_not_changed()
            master.assert_obj_not_in("slave")

        assert_not_reloaded()
        master.rewrite(
            """
        from . import slave
        global_var = 2
        """
        )

        reloader.reload(master)
        reloader.assert_objects(init, 'sandbox.master: Import', 'sandbox.slave: Import')
        reloader.assert_objects(slave, 'sandbox.slave.slave_global_var: Variable')
        reloader.assert_objects(master, 'sandbox.master.global_var: Variable', 'sandbox.master.slave: Import')

        reloader.assert_actions('Update Module: sandbox.master', 'Add Import: sandbox.master.slave')

        master.assert_obj_in("slave")

        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.global_var: Foreigner',
                                                  'sandbox.slave_module.slave_global_var: Variable')
            reloader.assert_objects(module, 'sandbox.module.global_var: Variable')
            assert module.device.global_var == 2
            assert slave_module.device.slave_global_var == 3
            init.assert_not_changed()
            slave_module.assert_not_changed()
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite("global_var = 0")

        with raises(ZeroDivisionError):
            reloader.reload(module)

        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.Optional: Foreigner',
                                                  'sandbox.slave_module.slave_var: Variable')
            reloader.assert_objects(module, 'sandbox.module.master_var: Variable')
            init.assert_not_changed()
            slave_module.assert_not_changed()
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
        from typing import Optional
        master_var = 2
        """
        )
        reloader.reload(module)
        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.Optional: Foreigner',
                                              'sandbox.slave_module.slave_var: Variable')
        reloader.assert_objects(module, 'sandbox.module.Optional: Foreigner', 'sandbox.module.master_var: Variable')

        reloader.assert_actions('Update Module: sandbox.module', 'Add Foreigner: sandbox.module.Optional')

        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
                                                  'sandbox.slave_module.tesla_car_1: Variable',
                                                  'sandbox.slave_module.tesla_car_2: Variable',
                                                  'sandbox.slave_module.tesla_car_3: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')
            init.assert_not_changed()
            slave_module.assert_not_changed()
            module.assert_not_changed()

        assert_not_reloaded()

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        slave_module.replace(
            '__all__ = ["tesla_car_1"]',
            '__all__ = ["tesla_car_1", "tesla_car_2", "tesla_car_3"]',
        )

        reloader.reload(slave_module)
        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
                                              'sandbox.slave_module.tesla_car_1: Variable',
                                              'sandbox.slave_module.tesla_car_2: Variable',
                                              'sandbox.slave_module.tesla_car_3: Variable')
        reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner',
                                        'sandbox.module.tesla_car_2: Foreigner',
                                        'sandbox.module.tesla_car_3: Foreigner')

        reloader.assert_actions('Add Foreigner: sandbox.module.tesla_car_2',
 'Add Foreigner: sandbox.module.tesla_car_3',
 'Update All: sandbox.slave_module.__all__',
 'Update Module: sandbox.module',
 'Update Module: sandbox.slave_module',
            ignore_order=True,
        )

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        reloader.rollback()
        assert_not_reloaded()

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
        tesla_car_2 = "Model X"
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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable',
                                                  'sandbox.slave_module.tesla_car_2: Variable',
                                                  'sandbox.slave_module.tesla_car_3: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner',
                                            'sandbox.module.tesla_car_2: Foreigner',
                                            'sandbox.module.tesla_car_3: Foreigner')
            slave_module.assert_not_changed()
            module.assert_not_changed()
            init.assert_not_changed()

        assert_not_reloaded()

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        slave_module.append('__all__ = ["tesla_car_1"]')

        reloader.reload(slave_module)

        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
                                              'sandbox.slave_module.tesla_car_1: Variable',
                                              'sandbox.slave_module.tesla_car_2: Variable',
                                              'sandbox.slave_module.tesla_car_3: Variable')
        reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')

        reloader.assert_actions('Add All: sandbox.slave_module.__all__',
                                 'Delete Foreigner: sandbox.module.tesla_car_2',
                                 'Delete Foreigner: sandbox.module.tesla_car_3',
                                 'Update Module: sandbox.module',
                                 'Update Module: sandbox.slave_module',
         ignore_order=True,
        )

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
                                                  'sandbox.slave_module.tesla_car_1: Variable',
                                                  'sandbox.slave_module.tesla_car_2: Variable',
                                                  'sandbox.slave_module.tesla_car_3: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')
            module.assert_obj_in("tesla_car_1")
            module.assert_obj_not_in("tesla_car_2")
            module.assert_obj_not_in("tesla_car_3")
            init.assert_not_changed()
            module.assert_not_changed()
            slave_module.assert_not_changed()

        assert_not_reloaded()

        slave_module.replace('__all__ = ["tesla_car_1"]', "")

        reloader.reload(slave_module)
        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable',
 'sandbox.slave_module.tesla_car_2: Variable',
 'sandbox.slave_module.tesla_car_3: Variable')
        reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner',
 'sandbox.module.tesla_car_2: Foreigner',
 'sandbox.module.tesla_car_3: Foreigner')

        reloader.assert_actions('Add Foreigner: sandbox.module.tesla_car_2',
             'Add Foreigner: sandbox.module.tesla_car_3',
             'Delete All: sandbox.slave_module.__all__',
             'Update Module: sandbox.module',
             'Update Module: sandbox.slave_module',
            ignore_order=True,
        )

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
                                                  'sandbox.slave_module.tesla_car_1: Variable',
                                                  'sandbox.slave_module.tesla_car_2: Variable',
                                                  'sandbox.slave_module.tesla_car_3: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')
            module.assert_obj_in("tesla_car_1")
            module.assert_obj_not_in("tesla_car_2")
            module.assert_obj_not_in("tesla_car_3")
            init.assert_not_changed()
            slave_module.assert_not_changed()
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite("")
        reloader.reload(module)
        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
 'sandbox.slave_module.tesla_car_1: Variable',
 'sandbox.slave_module.tesla_car_2: Variable',
 'sandbox.slave_module.tesla_car_3: Variable')
        reloader.assert_objects(module)

        reloader.assert_actions('Update Module: sandbox.module',
 'Delete Foreigner: sandbox.module.tesla_car_1')

        module.assert_obj_not_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")
        module.assert_obj_not_in("tesla_car_3")

        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')

            module.assert_obj_in("tesla_car_1")
            module.assert_obj_not_in("tesla_car_2")
            init.assert_not_changed()
            slave_module.assert_not_changed()
            module.assert_not_changed()

        assert_not_reloaded()

        slave_module.append('tesla_car_2 = "Model S"')

        reloader.reload(slave_module)
        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable',
                                              'sandbox.slave_module.tesla_car_2: Variable')
        reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner',
                                        'sandbox.module.tesla_car_2: Foreigner')

        reloader.assert_actions('Update Module: sandbox.slave_module',
                                'Add Variable: sandbox.slave_module.tesla_car_2',
                                'Update Module: sandbox.module',
                                'Add Foreigner: sandbox.module.tesla_car_2')

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")

        reloader.rollback()
        assert_not_reloaded()

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

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
                                                  'sandbox.slave_module.tesla_car_1: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')

            module.assert_obj_in("tesla_car_1")
            module.assert_obj_not_in("tesla_car_2")

            init.assert_not_changed()
            slave_module.assert_not_changed()
            module.assert_not_changed()

        assert_not_reloaded()

        slave_module.append('tesla_car_2 = "Model 3"')

        reloader.reload(slave_module)
        reloader.assert_objects(init, 'sandbox.module: Import', 'sandbox.slave_module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.__all__: All',
                                              'sandbox.slave_module.tesla_car_1: Variable',
                                              'sandbox.slave_module.tesla_car_2: Variable')
        reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')

        reloader.assert_actions('Update Module: sandbox.slave_module',
                                'Add Variable: sandbox.slave_module.tesla_car_2')

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_not_in("tesla_car_2")

        reloader.rollback()
        assert_not_reloaded()

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

        reloader.assert_objects(init, 'sandbox.module: Import',
                                      'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import')
        reloader.assert_objects(slave_module_2, 'sandbox.slave_module_2.car_2: Variable')
        reloader.assert_objects(slave_module_1, 'sandbox.slave_module_1.car_1: Variable')
        reloader.assert_objects(module, 'sandbox.module.car_1: Foreigner', 'sandbox.module.car_2: Foreigner')

        module.assert_obj_in("car_1")
        module.assert_obj_in("car_2")

        module.replace("from .slave_module_2 import *", "")
        reloader.reload(module)
        reloader.assert_objects(init, 'sandbox.module: Import',
                                      'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import')
        reloader.assert_objects(slave_module_2, 'sandbox.slave_module_2.car_2: Variable')
        reloader.assert_objects(slave_module_1, 'sandbox.slave_module_1.car_1: Variable')
        reloader.assert_objects(module, 'sandbox.module.car_1: Foreigner')

        reloader.assert_actions('Update Module: sandbox.module', 'Delete Foreigner: sandbox.module.car_2')
        module.assert_obj_in("car_1")
        module.assert_obj_not_in("car_2")

        slave_module_2.append("car_3 = 'Model X'")
        reloader.reload(slave_module_2)

        reloader.assert_objects(init, 'sandbox.module: Import',
                                      'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import')
        reloader.assert_objects(slave_module_2, 'sandbox.slave_module_2.car_2: Variable',
                                                'sandbox.slave_module_2.car_3: Variable')
        reloader.assert_objects(slave_module_1, 'sandbox.slave_module_1.car_1: Variable')
        reloader.assert_objects(module, 'sandbox.module.car_1: Foreigner')

        reloader.assert_actions('Update Module: sandbox.slave_module_2',
                                'Add Variable: sandbox.slave_module_2.car_3')

        module.assert_obj_in("car_1")
        module.assert_obj_not_in("car_2")
        module.assert_obj_not_in("car_3")

        reloader.rollback()

        reloader.assert_objects(init, 'sandbox.module: Import',
                                      'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import')
        reloader.assert_objects(slave_module_2, 'sandbox.slave_module_2.car_2: Variable')
        reloader.assert_objects(slave_module_1, 'sandbox.slave_module_1.car_1: Variable')
        reloader.assert_objects(module, 'sandbox.module.car_1: Foreigner')