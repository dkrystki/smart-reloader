import sys

from pytest import raises, mark

from tests import utils
from tests.utils import Module, MockedPartialReloader


class TestModules(utils.TestBase):
    def test_import_relative(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

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
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.slave_global_var: Variable')
            reloader.assert_objects(module, 'sandbox.module.slave_global_var: Foreigner',
                                            'sandbox.module.global_var: Variable')
            assert module.device.global_var == 2

        assert_not_reloaded()

        module.replace("global_var = 2", "global_var = 5")

        reloader.reload(module)
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.slave_global_var: Variable')
        reloader.assert_objects(module, 'sandbox.module.slave_global_var: Foreigner',
                                        'sandbox.module.global_var: Variable')

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
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        glob_var = 4
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.glob_var: Variable')
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
        reloader.assert_objects(module, 'sandbox.module.math: Import', 'sandbox.module.glob_var: Variable')

        reloader.assert_actions('Update Module: sandbox.module', 'Add Import: sandbox.module.math')

        module.assert_obj_in("math")

        reloader.rollback()
        assert_not_reloaded()

    def test_removed_import(self, sandbox):
        """
        We don't wanna remove imports because how python handles nested imports.
        """
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            import math
            """,
        )
        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.math: Import')
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite("")

        reloader.reload(module)

        assert_not_reloaded()
        reloader.assert_actions("Update Module: sandbox.module")

        module.assert_obj_in("math")
        reloader.rollback()
        assert_not_reloaded()

    def test_add_relative(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

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
            reloader.assert_objects(init, 'sandbox.slave: Import', 'sandbox.master: Import')
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
        reloader.assert_objects(init, 'sandbox.slave: Import', 'sandbox.master: Import')
        reloader.assert_objects(slave, 'sandbox.slave.slave_global_var: Variable')
        reloader.assert_objects(master, 'sandbox.master.slave: Import', 'sandbox.master.global_var: Variable')

        reloader.assert_actions('Update Module: sandbox.master', 'Add Import: sandbox.master.slave')

        master.assert_obj_in("slave")

        reloader.rollback()
        assert_not_reloaded()

    def test_error_rolls_back(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

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
        reloader = MockedPartialReloader(sandbox.parent)

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
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.Optional: Foreigner',
                                              'sandbox.slave_module.slave_var: Variable')
        reloader.assert_objects(module, 'sandbox.module.Optional: Foreigner', 'sandbox.module.master_var: Variable')

        reloader.assert_actions('Update Module: sandbox.module', 'Add Foreigner: sandbox.module.Optional')

        reloader.rollback()
        assert_not_reloaded()

    def test_update__all__(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

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
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader = MockedPartialReloader(sandbox)

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
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable',
                                                  'sandbox.slave_module.tesla_car_2: Variable',
                                                  'sandbox.slave_module.tesla_car_3: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner',
                                            'sandbox.module.tesla_car_2: Foreigner',
                                            'sandbox.module.tesla_car_3: Foreigner')

        assert_not_reloaded()

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")

        slave_module.append('__all__ = ["tesla_car_1"]')

        reloader.reload(slave_module)

        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable',
                                              'sandbox.slave_module.tesla_car_2: Variable',
                                              'sandbox.slave_module.tesla_car_3: Variable',
                                              'sandbox.slave_module.__all__: All')
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
        reloader = MockedPartialReloader(sandbox)

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
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable',
                                                  'sandbox.slave_module.tesla_car_2: Variable',
                                                  'sandbox.slave_module.tesla_car_3: Variable',
                                                  'sandbox.slave_module.__all__: All')
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
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader = MockedPartialReloader(sandbox.parent)

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
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader = MockedPartialReloader(sandbox)

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
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
            reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable')
            reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner')

            module.assert_obj_in("tesla_car_1")
            module.assert_obj_not_in("tesla_car_2")
            init.assert_not_changed()
            slave_module.assert_not_changed()
            module.assert_not_changed()

        assert_not_reloaded()

        init_orig = sys.modules[init.device.__name__]
        slave_orig = sys.modules[slave_module.device.__name__]
        module_orig = sys.modules[module.device.__name__]

        def assert_mod_id_not_changed():
            assert id(init_orig) == id(sys.modules[init.device.__name__])
            assert id(slave_orig) == id(sys.modules[slave_module.device.__name__])
            assert id(module_orig) == id(sys.modules[module.device.__name__])

        assert_mod_id_not_changed()

        # Add first object
        slave_module.append('tesla_car_2 = "Model E"\n')

        reloader.reload(slave_module)
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        assert_mod_id_not_changed()

        # Add second object
        slave_module.append('tesla_car_3 = "Model X"\n')

        reloader.reload(slave_module)
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
        reloader.assert_objects(slave_module, 'sandbox.slave_module.tesla_car_1: Variable',
                                'sandbox.slave_module.tesla_car_2: Variable',
                                'sandbox.slave_module.tesla_car_3: Variable')
        reloader.assert_objects(module, 'sandbox.module.tesla_car_1: Foreigner',
                                'sandbox.module.tesla_car_2: Foreigner',
                                'sandbox.module.tesla_car_3: Foreigner')

        reloader.assert_actions('Update Module: sandbox.slave_module',
                                'Add Variable: sandbox.slave_module.tesla_car_3',
                                'Update Module: sandbox.module',
                                'Add Foreigner: sandbox.module.tesla_car_3')

        module.assert_obj_in("tesla_car_1")
        module.assert_obj_in("tesla_car_2")
        module.assert_obj_in("tesla_car_3")
        assert_mod_id_not_changed()

    def test_added_object_not_in_all(self, sandbox):
        reloader = MockedPartialReloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import slave_module
        from . import module
        """
        )

        slave_module = Module(
            "slave_module.py",
            """
        __all__ = ["tesla_car_1"]
        tesla_car_1 = "Model S"
        """
        )

        module = Module(
            "module.py",
            """
        from .slave_module import *
        """
        )
        init.load()
        slave_module.load_from(init)
        module.load_from(init)

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader.assert_objects(init, 'sandbox.slave_module: Import', 'sandbox.module: Import')
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
        reloader = MockedPartialReloader(sandbox)

        init = Module(
            "__init__.py",
            """
        from . import slave_module_1
        from . import slave_module_2
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

        reloader.assert_objects(init, 'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import',
                                      'sandbox.module: Import')
        reloader.assert_objects(slave_module_2, 'sandbox.slave_module_2.car_2: Variable')
        reloader.assert_objects(slave_module_1, 'sandbox.slave_module_1.car_1: Variable')
        reloader.assert_objects(module, 'sandbox.module.car_1: Foreigner', 'sandbox.module.car_2: Foreigner')

        module.assert_obj_in("car_1")
        module.assert_obj_in("car_2")

        module.replace("from .slave_module_2 import *", "")
        reloader.reload(module)
        reloader.assert_objects(init, 'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import',
                                      'sandbox.module: Import')
        reloader.assert_objects(slave_module_2, 'sandbox.slave_module_2.car_2: Variable')
        reloader.assert_objects(slave_module_1, 'sandbox.slave_module_1.car_1: Variable')
        reloader.assert_objects(module, 'sandbox.module.car_1: Foreigner')

        reloader.assert_actions('Update Module: sandbox.module', 'Delete Foreigner: sandbox.module.car_2')
        module.assert_obj_in("car_1")
        module.assert_obj_not_in("car_2")

        slave_module_2.append("car_3 = 'Model X'")
        reloader.reload(slave_module_2)

        reloader.assert_objects(init, 'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import',
                                      'sandbox.module: Import')
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

        reloader.assert_objects(init, 'sandbox.slave_module_1: Import',
                                      'sandbox.slave_module_2: Import',
                                      'sandbox.module: Import')
        reloader.assert_objects(slave_module_2, 'sandbox.slave_module_2.car_2: Variable')
        reloader.assert_objects(slave_module_1, 'sandbox.slave_module_1.car_1: Variable')
        reloader.assert_objects(module, 'sandbox.module.car_1: Foreigner')

    def test_swap_modules(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        init = Module(
            "__init__.py",
            """
        from . import cupcake as dessert
        """,
        )

        cupcake = Module(
            "cupcake.py",
            """
        name = "cupcake"
        """,
        )

        muffin = Module(
            "muffin.py",
            """
        name = "muffin"
        """,
        )
        init.load()

        def assert_not_reloaded():
            assert init.device.dessert.name == "cupcake"
            reloader.assert_objects(init, 'sandbox.cupcake: Import', 'sandbox.dessert: Import')

        assert_not_reloaded()

        reloader.reload(init)
        reloader.assert_actions('Update Module: sandbox',)

        init.rewrite(
            """
        from . import muffin as dessert
        """
        )

        reloader.reload(init)
        reloader.assert_objects(init, 'sandbox.cupcake: Import', 'sandbox.muffin: Import', 'sandbox.dessert: Import')

        assert init.device.dessert.name == "muffin"

        reloader.assert_actions('Update Module: sandbox', 'Update Import: sandbox.dessert')
        reloader.assert_objects(init, 'sandbox.cupcake: Import', 'sandbox.muffin: Import', 'sandbox.dessert: Import')

        reloader.rollback()
        assert_not_reloaded()

    def test_reloading_out_of_sync_modules(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        init = Module(
            "__init__.py",
            """
        from . import cakeshop
        from . import cake
        from . import decoration
        """,
        )

        cakeshop = Module(
            "cakeshop.py",
            """
        from . import cake
        total_size = 1 / cake.size
        """,
        )
        cake = Module(
            "cake.py",
            """
        from . import decoration
        size =  decoration.size * 10
        """,
        )

        decoration = Module(
            "decoration.py",
            """
        size = 10
        """,
        )
        init.load()
        cakeshop.load_from(init)
        cake.load_from(init)
        decoration.load_from(init)

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.cakeshop: Import',
                                          'sandbox.cake: Import',
                                          'sandbox.decoration: Import')

            reloader.assert_objects(cakeshop, 'sandbox.cakeshop.cake: Import', 'sandbox.cakeshop.total_size: Variable')
            reloader.assert_objects(cake, 'sandbox.cake.decoration: Import', 'sandbox.cake.size: Variable')
            reloader.assert_objects(decoration, 'sandbox.decoration.size: Variable')

        assert_not_reloaded()

        decoration.rewrite("size = 0")

        with raises(ZeroDivisionError):
            reloader.reload(decoration)

        reloader.assert_actions('Update Module: sandbox.decoration',
                                'Update Variable: sandbox.decoration.size',
                                'Update Module: sandbox.cake',
                                'Update Variable: sandbox.cake.size',
                                'Update Module: sandbox.cakeshop')

        reloader.rollback()
        assert_not_reloaded()

        cakeshop.rewrite("""
        from . import cake
        total_size = cake.size * 10
        """)
        reloader.reload(cakeshop)
        reloader.assert_actions('Update Module: sandbox.cakeshop',
                                'Update Variable: sandbox.cakeshop.total_size',
                                'Update Module: sandbox.decoration',
                                'Update Variable: sandbox.decoration.size',
                                'Update Module: sandbox.cake',
                                'Update Variable: sandbox.cake.size',
                                )

        assert cakeshop.device.total_size == 1000
        reloader.rollback()

        assert_not_reloaded()
        assert cakeshop.device.total_size == 0.01
