from tests import utils
from tests.utils import Module, Reloader


class TestFunctions(utils.TestBase):
    def test_added_function(self, sandbox):
        reloader = Reloader(sandbox)

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

        module.append(
            """
                def fun2(arg1: str, arg2: str) -> str:
                    return f"{arg1}_{arg2}_{id(global_var)}"
                """
        )

        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Add: Function: module.fun2")

        module.assert_obj_in("fun")
        module.assert_obj_in("fun2")

        assert module.device.fun("str1", "str2") == module.device.fun2("str1", "str2")

    def test_modified_function(self, sandbox):
        reloader = Reloader(sandbox)

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

        module.rewrite(
            """
        import math

        global_var = 2

        def fun(arg1: str) -> str:
            return f"{arg1}_{id(global_var)}"
        """
        )

        reloader.reload(module)
        reloader.assert_actions(
            "Update: Module: module", "Update: Function: module.fun"
        )

        module.assert_obj_in("fun")

        global_var_id = id(module.device.global_var)

        assert module.device.fun("str1").endswith(str(global_var_id))
        assert id(module.device.fun) == fun_id_before

    def test_deleted_function(self, sandbox):
        reloader = Reloader(sandbox)

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

        assert hasattr(module.device, "fun1")
        assert hasattr(module.device, "fun2")

        module.rewrite(
            """
        def fun1():
            return 12
        """
        )

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module", "Delete: Function: module.fun2"
        )

        assert hasattr(module.device, "fun1")
        assert not hasattr(module.device, "fun2")

    def test_renamed_function(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun1():
            return 12
        """,
        )

        module.load()

        assert hasattr(module.device, "fun1")
        assert not hasattr(module.device, "fun_renamed")

        module.rewrite(
            """
        def fun_renamed():
            return 12
        """
        )

        reloader.reload(module)
        reloader.assert_actions(
            "Update: Module: module",
            "Add: Function: module.fun_renamed",
            "Delete: Function: module.fun1",
        )

        assert not hasattr(module.device, "fun1")
        assert hasattr(module.device, "fun_renamed")

    def test_uses_class(self, sandbox):
        reloader = Reloader(sandbox)

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

        module.replace('car = Car("red")', 'car = Car("green")')

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module", "Update: Function: module.fun"
        )

        assert id(module.device.Car) == car_class_id
        assert id(module.device.fun) == fun_id

        assert isinstance(module.device.fun(), module.device.Car)
        assert isinstance(module.device.fun(), module.device.Car)

        assert module.device.fun().colour == "green"

    def test_uses_function(self, sandbox):
        reloader = Reloader(sandbox)

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
        assert module.device.fun() == 15

        module.replace("return 5", "return 10")

        reloader.reload(module)
        reloader.assert_actions(
            "Update: Module: module", "Update: Function: module.other_fun"
        )

        assert module.device.fun() == 20

    def test_uses_function_2(self, sandbox):
        reloader = Reloader(sandbox)

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
        assert module.device.fun() == 15

        module.rewrite(
            """
        def other_fun():
            return 10

        def fun():
            return other_fun() + 15
        """
        )

        reloader.reload(module)
        reloader.assert_actions(
            "Update: Module: module",
            "Update: Function: module.other_fun",
            "Update: Function: module.fun",
        )

        assert module.device.fun() == 25

    def test_uses_added_function(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        def fun():
            return 10
        """,
        )

        module.load()
        assert module.device.fun() == 10

        module.rewrite(
            """
        def other_fun():
            return 10

        def fun():
            return other_fun() + 10
        """
        )

        reloader.reload(module)
        reloader.assert_actions(
            "Update: Module: module",
            "Add: Function: module.other_fun",
            "Update: Function: module.fun",
        )

        assert module.device.fun() == 20

    def test_moves_functions_first_lines(self):
        assert False
