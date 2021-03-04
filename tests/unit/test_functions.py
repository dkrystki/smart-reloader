from tests import utils
from tests.utils import Module, MockedPartialReloader


class TestFunctions(utils.TestBase):
    def test_added_function(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        import math

        global_var = 2

        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function', 'module.global_var: Variable', 'module.math: Import')
            module.assert_not_changed()

        assert_not_reloaded()

        module.append(
            """
        def fun2(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun2: Function',
                                         'module.fun: Function',
                                         'module.global_var: Variable',
                                         'module.math: Import')

        reloader.assert_actions("Update Module: module", "Add Function: module.fun2")

        module.assert_obj_in("fun")
        module.assert_obj_in("fun2")

        assert module.device.fun("str1", "str2") == module.device.fun2("str1", "str2")

        reloader.rollback()
        assert_not_reloaded()

    def test_modified_function(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        import math

        global_var = 2

        def fun(arg1: str, arg2: str) -> str:
            return f"{arg1}_{arg2}_{id(global_var)}"
        """,
        )
        module.load()

        fun_id_before = id(module.device.fun)
        global_var_id = id(module.device.global_var)

        def assert_not_reloaded():
            assert module.device.fun("str1", "str2").endswith(str(global_var_id))
            assert module.device.fun("str1", "str2").startswith("str1_str2")
            assert id(module.device.fun) == fun_id_before
            reloader.assert_objects(module, 'module.fun: Function', 'module.global_var: Variable', 'module.math: Import')
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
        import math

        global_var = 2

        def fun(arg1: str) -> str:
            return f"{arg1}_{id(global_var)}"
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun: Function', 'module.global_var: Variable', 'module.math: Import')
        reloader.assert_actions(
            "Update Module: module", "Update Function: module.fun"
        )

        module.assert_obj_in("fun")

        assert module.device.fun("str1").endswith(str(global_var_id))
        assert id(module.device.fun) == fun_id_before

        reloader.rollback()
        assert_not_reloaded()

    def test_deleted_function(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun1():
            return 12

        def fun2():
            return 22
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun1: Function', 'module.fun2: Function')
            module.assert_not_changed()

        module.rewrite(
            """
        def fun1():
            return 12
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun1: Function')

        reloader.assert_actions(
            "Update Module: module", "Delete Function: module.fun2"
        )

        assert hasattr(module.device, "fun1")
        assert not hasattr(module.device, "fun2")

        reloader.rollback()
        assert_not_reloaded()

    def test_renamed_function(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun1():
            return 12
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun1: Function')
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
        def fun_renamed():
            return 12
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun_renamed: Function')
        reloader.assert_actions(
            "Update Module: module",
            "Add Function: module.fun_renamed",
            "Delete Function: module.fun1",
        )

        assert not hasattr(module.device, "fun1")
        assert hasattr(module.device, "fun_renamed")

        reloader.rollback()
        assert_not_reloaded()

    def test_uses_class(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Car:
            engine_power = 1
            colour: str

            def __init__(self, colour: str):
                self.colour = colour

        def fun():
            car = Car("red")
            return car 
        """,
        )

        module.load()

        car_class_id = id(module.device.Car)
        fun_id = id(module.device.fun)

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Car.__init__: Method',
                                            'module.Car.engine_power: ClassVariable',
                                            'module.Car: Class',
                                            'module.fun: Function')
            assert module.device.fun().colour == "red"
            assert id(module.device.Car) == car_class_id
            assert id(module.device.fun) == fun_id
            assert isinstance(module.device.fun(), module.device.Car)
            module.assert_not_changed()

        assert_not_reloaded()

        module.replace('car = Car("red")', 'car = Car("green")')

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Car.__init__: Method',
                                        'module.Car.engine_power: ClassVariable',
                                        'module.Car: Class',
                                        'module.fun: Function')

        reloader.assert_actions(
            "Update Module: module", "Update Function: module.fun"
        )

        assert id(module.device.Car) == car_class_id
        assert id(module.device.fun) == fun_id

        assert isinstance(module.device.fun(), module.device.Car)

        assert module.device.fun().colour == "green"

        reloader.rollback()
        assert_not_reloaded()

    def test_uses_function(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def other_fun():
            return 5

        def fun():
            return other_fun() + 10
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function', 'module.other_fun: Function')
            module.assert_not_changed()
            assert module.device.fun() == 15

        assert_not_reloaded()

        module.replace("return 5", "return 10")

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun: Function', 'module.other_fun: Function')
        reloader.assert_actions(
            "Update Module: module", "Update Function: module.other_fun"
        )

        assert module.device.fun() == 20

        reloader.rollback()
        assert_not_reloaded()

    def test_uses_function_2(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def other_fun():
            return 5

        def fun():
            return other_fun() + 10
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function', 'module.other_fun: Function')
            module.assert_not_changed()
            assert module.device.fun() == 15

        assert_not_reloaded()

        module.rewrite(
            """
        def other_fun():
            return 10

        def fun():
            return other_fun() + 15
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun: Function', 'module.other_fun: Function')

        reloader.assert_actions(
            "Update Module: module",
            "Update Function: module.other_fun",
            "Update Function: module.fun",
        )

        assert module.device.fun() == 25

        reloader.rollback()

    def test_uses_added_function(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun():
            return 10
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function')
            module.assert_not_changed()
            assert module.device.fun() == 10

        assert_not_reloaded()

        module.rewrite(
            """
        def other_fun():
            return 10

        def fun():
            return other_fun() + 10
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.other_fun: Function', 'module.fun: Function')

        reloader.assert_actions(
            "Update Module: module",
            "Add Function: module.other_fun",
            "Update Function: module.fun",
        )

        assert module.device.fun() == 20

        reloader.rollback()
        assert_not_reloaded()

    def test_add_closure(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun():
            return 10
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function')
            assert module.device.fun() == 10
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
        def fun():
            def get_number():
                return 5
            return 10 + get_number()
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun: Function')

        reloader.assert_actions('Update Module: module', 'Update Function: module.fun')
        assert module.device.fun() == 15

        reloader.rollback()
        assert_not_reloaded()

    def test_edit_closure(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun():
            def get_number():
                return 5
            return 10 + get_number()
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function')
            assert module.device.fun() == 15
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
        def fun():
            def get_number():
                return 15
            return 15 + get_number()
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun: Function')

        reloader.assert_actions('Update Module: module', 'Update Function: module.fun')
        assert module.device.fun() == 30

        reloader.rollback()
        assert_not_reloaded()

    def test_add_lambda(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module)
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
        fun = lambda x: 10 + x
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun: Function')
        reloader.assert_actions('Update Module: module', 'Add Function: module.fun')
        assert module.device.fun(5) == 15

        reloader.rollback()
        assert_not_reloaded()

    def test_edit_lambda(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        fun = lambda x: 10 + x
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function')
            module.assert_not_changed()
            assert module.device.fun(5) == 15

        assert_not_reloaded()

        module.rewrite(
            """
        fun = lambda x: x * 10
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.fun: Function')
        reloader.assert_actions('Update Module: module', 'Update Function: module.fun')
        assert module.device.fun(5) == 50

        reloader.rollback()
        assert_not_reloaded()

    def test_moves_functions_first_lines(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun():
            return 10
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.fun: Function')
            module.assert_not_changed()

        assert module.device.fun.__code__.co_firstlineno == 2
        assert_not_reloaded()

        module.rewrite(
            """
        def added_fun():
            return 5
            
        def fun():
            return 10
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.added_fun: Function', 'module.fun: Function')
        reloader.assert_actions('Update Module: module',
                                'Add Function: module.added_fun',
                                'Move Function: module.fun')

        assert module.device.fun.__code__.co_firstlineno == 5
        reloader.rollback()
        assert_not_reloaded()
        assert module.device.fun.__code__.co_firstlineno == 5

    def test_add_decorator(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            def eat_more(func):
                def wrapped_func():
                    return func() + 10
                return wrapped_func

            def how_many_eat():
                return 1
                
            ref_fun = how_many_eat
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.eat_more: Function',
                                            'module.how_many_eat: Function',
                                            'module.ref_fun: Reference')
            module.assert_not_changed()
            assert module.device.how_many_eat() == 1
            assert module.device.ref_fun() == 1

        assert_not_reloaded()

        module.rewrite(
            """
            def eat_more(func):
                def wrapped_func():
                    return func() + 10
                return wrapped_func

            @eat_more
            def how_many_eat():
                return 1
                
            ref_fun = how_many_eat
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.eat_more: Function',
                                        'module.how_many_eat: Function',
                                        'module.ref_fun: Reference')
        reloader.assert_actions('Update Module: module', 'DeepUpdate Function: module.how_many_eat')

        assert module.device.how_many_eat() == 11
        assert module.device.ref_fun() == 11

        reloader.rollback()
        assert_not_reloaded()
