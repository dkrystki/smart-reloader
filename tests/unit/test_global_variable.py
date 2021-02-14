from pytest import raises

from tests import utils
from tests.utils import Module, Reloader
from smartreload import dependency_watcher


class TestGlobalVariable(utils.TestBase):
    def test_modified_global_var_with_dependencies(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import carwash
        from . import car
        from . import accounting
        from . import client
        from . import boss
        """,
        )

        carwash = Module(
            "carwash.py",
            """
        sprinkler_n = 3
        money = 1e3
        """,
        )

        car = Module(
            "car.py",
            """
        from .carwash import sprinkler_n

        car_sprinklers = sprinkler_n / 3
        """,
        )

        accounting = Module(
            "accounting.py",
            """
        from .car import car_sprinklers

        sprinklers_from_accounting = car_sprinklers * 10
        """,
        )

        client = Module(
            "client.py",
            """
        from . import carwash

        client_car_sprinklers = carwash.sprinkler_n / 3
        """,
        )

        boss = Module(
            "boss.py",
            """
        from . import carwash

        actual_money = carwash.money * 5
        """,
        )

        init.load()

        carwash.load_from(init)
        car.load_from(init)
        accounting.load_from(init)

        client.load_from(init)
        boss.load_from(init)

        carwash.replace("sprinkler_n = 3", "sprinkler_n = 6")

        reloader.reload(carwash)
        reloader.assert_actions(
            "Update: Module: sandbox.carwash",
            "Update: Variable: sandbox.carwash.sprinkler_n",
            "Update: Module: sandbox.car",
            "Update: Variable: sandbox.car.sprinkler_n",
            "Update: Variable: sandbox.car.car_sprinklers",
            "Update: Module: sandbox.accounting",
            "Update: Variable: sandbox.accounting.car_sprinklers",
            "Update: Variable: sandbox.accounting.sprinklers_from_accounting",
            "Update: Module: sandbox.client",
            "Update: Variable: sandbox.client.client_car_sprinklers",
        )

        assert carwash.device.sprinkler_n == 6
        assert car.device.sprinkler_n == 6
        assert car.device.car_sprinklers == 2
        assert accounting.device.car_sprinklers == 2
        assert accounting.device.sprinklers_from_accounting == 20
        assert client.device.client_car_sprinklers == 2

        # Test rollback
        reloader.rollback()
        carwash.assert_not_changed()
        init.assert_not_changed()
        car.assert_not_changed()
        accounting.assert_not_changed()
        client.assert_not_changed()
        boss.assert_not_changed()

    def test_modified_import_star(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import carwash
        from . import car
        """,
        )

        carwash = Module(
            "carwash.py",
            """
        sprinkler_n = 3
        """,
        )

        car = Module(
            "car.py",
            """
        from .carwash import *
        
        car_sprinklers = sprinkler_n / 3
        """,
        )

        init.load()
        carwash.load_from(init)
        car.load_from(init)

        carwash.rewrite(
            """
        sprinkler_n = 6
        """
        )

        reloader.reload(carwash)

        reloader.assert_actions(
            "Update: Module: sandbox.carwash",
            "Update: Variable: sandbox.carwash.sprinkler_n",
            "Update: Module: sandbox.car",
            "Update: Variable: sandbox.car.sprinkler_n",
            "Update: Variable: sandbox.car.car_sprinklers",
        )

        assert carwash.device.sprinkler_n == 6
        assert car.device.car_sprinklers == 2

        # Test rollback
        reloader.rollback()
        carwash.assert_not_changed()
        car.assert_not_changed()

    def test_modified_import_star_nested_twice(self, sandbox):
        reloader = Reloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import carwash
        from . import container
        from . import car
        """,
        )

        carwash = Module(
            "carwash.py",
            """
        sprinkler_n = 3
        """,
        )

        container = Module(
            "container.py",
            """
        from .carwash import *
        """,
        )

        car = Module(
            "car.py",
            """
        from .container import *
        
        car_sprinklers = sprinkler_n / 3
        """,
        )

        init.load()
        carwash.load_from(init)
        container.load_from(init)
        car.load_from(init)

        carwash.rewrite(
            """
        sprinkler_n = 6
        """
        )

        reloader.reload(carwash)

        reloader.assert_actions(
            "Update: Module: sandbox.carwash",
            "Update: Variable: sandbox.carwash.sprinkler_n",
            "Update: Module: sandbox.container",
            "Update: Variable: sandbox.container.sprinkler_n",
            "Update: Module: sandbox.car",
            "Update: Variable: sandbox.car.sprinkler_n",
            "Update: Variable: sandbox.car.car_sprinklers",
        )

        assert carwash.device.sprinkler_n == 6
        assert car.device.car_sprinklers == 2

        # Test rollback
        reloader.rollback()
        init.assert_not_changed()
        carwash.assert_not_changed()
        container.assert_not_changed()
        car.assert_not_changed()

    def test_added_global_var(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        global_var1 = 1
        """,
        )

        module.load()

        module.append("global_var2 = 2")

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module", "Add: Variable: module.global_var2"
        )

        module.assert_obj_in("global_var1")
        module.assert_obj_in("global_var2")

        assert module.device.global_var1 == 1
        assert module.device.global_var2 == 2

        # Test rollback
        reloader.rollback()
        module.assert_not_changed()

    def test_fixes_class_references(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        class Car:
            pass

        car_class = None
        """,
        )

        module.load()

        old_Car_class = module.device.Car

        module.replace("car_class = None", "car_class = Car")

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module", "Update: Variable: module.car_class"
        )

        assert module.device.Car is old_Car_class
        assert module.device.car_class is module.device.Car

        # Test rollback
        reloader.rollback()
        module.assert_not_changed()

    def test_fixes_function_references(self, sandbox):
        reloader = Reloader(sandbox.parent)

        module = Module(
            "module.py",
            """
        def fun():
            return 10

        car_fun = None
        """,
        )

        module.load()
        old_fun = module.device.fun

        module.replace("car_fun = None", "car_fun = fun")

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module",
            "Update: Variable: module.car_fun",
        )

        assert module.device.fun is old_fun
        assert module.device.car_fun is module.device.fun

        # Test rollback
        reloader.rollback()
        module.assert_not_changed()

    def test_modified_global_var(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        sprinkler_n = 1

        def some_fun():
            return "Some Fun"

        sample_dict = {
            "sprinkler_n_plus_1": sprinkler_n + 1,
            "sprinkler_n_plus_2": sprinkler_n + 2,
            "lambda_fun": lambda x: sprinkler_n + x,
            "fun": some_fun
        }

        def print_sprinkler():
            return (f"There is {sprinkler_n} sprinkler."
             f"({sample_dict['sprinkler_n_plus_1']}, {sample_dict['sprinkler_n_plus_2']})")

        class Car:
            car_sprinkler_n = sprinkler_n
        """,
        )

        module.load()

        print_sprinkler_id = id(module.device.print_sprinkler)
        lambda_fun_id = id(module.device.sample_dict["lambda_fun"])
        some_fun_id = id(module.device.some_fun)

        def assert_not_reloaded():
            assert module.device.sprinkler_n == 1

            assert print_sprinkler_id == id(module.device.print_sprinkler)
            assert module.device.Car.car_sprinkler_n == 1
            assert lambda_fun_id == id(module.device.sample_dict["lambda_fun"])
            assert some_fun_id == id(module.device.some_fun)
            assert module.device.sample_dict == {
                "sprinkler_n_plus_1": 2,
                "sprinkler_n_plus_2": 3,
                "lambda_fun": module.device.sample_dict["lambda_fun"],
                "fun": module.device.some_fun,
            }

        assert_not_reloaded()

        module.replace("sprinkler_n = 1", "sprinkler_n = 2")

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module",
            "Update: Variable: module.sprinkler_n",
            "Update: DictionaryItem: module.sample_dict.sprinkler_n_plus_1",
            "Update: DictionaryItem: module.sample_dict.sprinkler_n_plus_2",
            "Update: ClassVariable: module.Car.car_sprinkler_n",
        )

        assert print_sprinkler_id == id(module.device.print_sprinkler)
        assert module.device.Car.car_sprinkler_n == 2
        assert lambda_fun_id == id(module.device.sample_dict["lambda_fun"])
        assert some_fun_id == id(module.device.some_fun)
        assert module.device.sample_dict == {
            "sprinkler_n_plus_1": 3,
            "sprinkler_n_plus_2": 4,
            "lambda_fun": module.device.sample_dict["lambda_fun"],
            "fun": module.device.some_fun,
        }

        # Test rollback
        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_deleted_global_var(self, sandbox):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        cars_n = 1
        sprinkler_n = 1
        """,
        )

        module.load()

        module.delete("sprinkler_n = 1")

        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module", "Delete: Variable: module.sprinkler_n"
        )

        assert not hasattr(module.device, "sprinkler_n")
        assert hasattr(module.device, "cars_n")

        # Test rollback
        reloader.rollback()
        module.assert_not_changed()
