from tests import utils
from tests.utils import Module, Reloader


class TestClasses(utils.TestBase):
    def test_modified_class_variable_with_dependencies(self, sandbox):
        init = Module("__init__.py",
        """
        from . import carwash
        from . import car
        """
        )

        carwash = Module("carwash.py",
        """
        import math

        class Carwash:
            sprinkler_n = 3
        """
        )

        car = Module("car.py",
        """
        import math
        from .carwash import Carwash

        class Car: 
            car_sprinklers = Carwash.sprinkler_n / 3
        """
        )

        init.load()

        carwash.device = init.device.carwash
        car.device = init.device.car

        assert carwash.device.Carwash.sprinkler_n == 3
        assert car.device.Car.car_sprinklers == 1

        carwash.replace("sprinkler_n = 3", "sprinkler_n = 6")

        reloader = Reloader(sandbox.parent)
        reloader.reload(carwash)

        reloader.assert_actions(
            "Update: Module: sandbox.carwash",
            "Update: ClassVariable: sandbox.carwash.Carwash.sprinkler_n",
            "Update: Module: sandbox.car",
            "Update: ClassVariable: sandbox.car.Car.car_sprinklers"
        )

        assert carwash.device.Carwash.sprinkler_n == 6
        assert car.device.Car.car_sprinklers == 2

    def test_modified_class_attr(self, sandbox):
        module = Module("module.py",
            """
        import math

        class CarwashBase:
            sprinklers_n: int = 12

            def print_sprinklers(self) -> str:
                return f"There are {self.sprinklers_n} sprinklers (Base)."

        class Carwash(CarwashBase):
            sprinklers_n: int = 22

            def print_sprinklers(self) -> str:
                return f"There are {self.sprinklers_n} sprinklers (Inherited)."
        """
        )

        module.load()

        print_sprinklers_id = id(module.device.CarwashBase.print_sprinklers)

        module.rewrite(
                """
            import math

            class CarwashBase:
                sprinklers_n: int = 55

                def print_sprinklers(self) -> str:
                    return f"There are {self.sprinklers_n} sprinklers (Base)."

            class Carwash(CarwashBase):
                sprinklers_n: int = 77

                def print_sprinklers(self) -> str:
                    return f"There are {self.sprinklers_n} sprinklers (Inherited)."
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Update: ClassVariable: module.CarwashBase.sprinklers_n",
                "Update: ClassVariable: module.Carwash.sprinklers_n",
        )

        assert module.device.CarwashBase.sprinklers_n == 55
        assert module.device.Carwash.sprinklers_n == 77
        assert print_sprinklers_id == id(module.device.CarwashBase.print_sprinklers)

    def test_modified_init_with_super(self, sandbox):
        module = Module("module.py",
                """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash(CarwashBase):
            pass
        """
        )

        module.load()
        module.rewrite(
                """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash(CarwashBase):
            def __init__(self, car_n: int) -> None:
                super().__init__()
                self.car_n = car_n
        """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module",
            "Delete: Class: module.Carwash",
            "Add: Class: module.Carwash"
        )

        assert module.device.Carwash(30).car_n == 30

    def test_add_base_class(self, sandbox):
        module = Module("module.py",
        """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash:
            def __init__(self, car_n: int) -> None:
                self.car_n = car_n
        """
        )

        module.load()

        module.rewrite(
                """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash(CarwashBase):
            def __init__(self, car_n: int) -> None:
                super().__init__()
                self.car_n = car_n
        """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Delete: Class: module.Carwash",
                "Add: Class: module.Carwash",
        )

        assert isinstance(module.device.Carwash(30), module.device.CarwashBase)
        assert module.device.Carwash(30).car_n == 30

    def test_type_as_attribute(self, sandbox):
        module = Module("module.py",
            """
        class Carwash:
            name_type = int
        """
        )

        module.load()
        assert module.device.Carwash.name_type is int

        module.replace("name_type = int", "name_type = str")

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Update: ClassVariable: module.Carwash.name_type"
        )

        assert module.device.Carwash.name_type is str

    def test_added_class(self, sandbox):
        module = Module("module.py",
        """
        a = 1
        """
        )

        module.load()

        module.rewrite(
        """
        a = 1

        class Carwash:
            sprinklers_n: int = 55

            def print_sprinklers(self) -> str:
                return 20
        """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Add: Class: module.Carwash")

        assert module.device.Carwash.sprinklers_n == 55
        assert module.device.Carwash().print_sprinklers() == 20

    def test_recursion(self, sandbox):
        module = Module("module.py",
        """
        class Carwash:
            class_attr = 2

        Carwash.klass = Carwash 
        """
        )

        module.load()

        reloader = Reloader(sandbox)
        reloader.reload(module)

    def test_recursion_two_deep(self, sandbox):
        module = Module("module.py",
        """
        class Carwash:
            class_attr = 2

            class Car:
                class_attr2 = 13

        Carwash.Car.klass = Carwash 
        """
        )

        module.load()

        reloader = Reloader(sandbox)
        reloader.reload(module)

    def test_added_class_attr(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                sprinklers_n: int = 22

                def fun(self) -> str:
                    return 12
            """
        )

        module.load()

        assert hasattr(module.device.Carwash, "sprinklers_n")
        assert not hasattr(module.device.Carwash, "cars_n")

        # First edit
        module.rewrite(
            """
        class Carwash:
            sprinklers_n: int = 22
            cars_n: int = 15

            def fun(self) -> str:
                return 12
        """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module", "Add: ClassVariable: module.Carwash.cars_n"
        )

        assert hasattr(module.device.Carwash, "sprinklers_n")
        assert hasattr(module.device.Carwash, "cars_n")

    def test_deleted_class_attr(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                sprinklers_n: int = 22
                cars_n: int = 15

                def fun(self) -> str:
                    return 12
            """
        )

        module.load()

        assert hasattr(module.device.Carwash, "sprinklers_n")
        assert hasattr(module.device.Carwash, "cars_n")

        # First edit
        module.rewrite(
                """
            class Carwash:
                sprinklers_n: int = 22

                def fun(self) -> str:
                    return 12
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Delete: ClassVariable: module.Carwash.cars_n"
        )

        assert hasattr(module.device.Carwash, "sprinklers_n")
        assert not hasattr(module.device.Carwash, "cars_n")

    def test_modified_method(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                @classmethod
                def print_sprinklers_cls(cls) -> str:
                    return f"There is one sprinkler (Cls)."

                def print_sprinklers(self) -> str:
                    return f"There is one sprinkler."
            """
        )

        module.load()
        reffered_print_sprinklers_cls = module.device.Carwash.print_sprinklers_cls
        assert module.device.Carwash.print_sprinklers_cls() == "There is one sprinkler (Cls)."
        assert reffered_print_sprinklers_cls() == "There is one sprinkler (Cls)."
        assert module.device.Carwash().print_sprinklers() == "There is one sprinkler."

        print_sprinklers_id = id(module.device.Carwash.print_sprinklers)

        module.rewrite(
                """
            class Carwash:
                @classmethod
                def print_sprinklers_cls(cls) -> str:
                    return f"There are 5 sprinklers (Cls)."

                def print_sprinklers(self) -> str:
                    return f"There are 5 sprinklers."
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Update: ClassMethod: module.Carwash.print_sprinklers_cls",
                "Update: Method: module.Carwash.print_sprinklers",
        )

        assert module.device.Carwash.print_sprinklers_cls() == "There are 5 sprinklers (Cls)."
        assert reffered_print_sprinklers_cls() == "There are 5 sprinklers (Cls)."
        assert module.device.Carwash().print_sprinklers() == "There are 5 sprinklers."
        assert print_sprinklers_id == id(module.device.Carwash.print_sprinklers)

    def test_modified_repr(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                def __repr__(self) -> str:
                    return "Carwash"
            """
        )

        module.load()
        assert repr(module.device.Carwash()) == "Carwash"

        module.rewrite(
            """
            class Carwash:
                def __repr__(self) -> str:
                    return "MyCarwash"
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Update: Method: module.Carwash.__repr__")

        assert repr(module.device.Carwash()) == "MyCarwash"

    def test_uses_other_classes(self, sandbox):
        module = Module("module.py",
                """
            class Engine:
                brand: str

                def __init__(self, brand: str = "Tesla"):
                    self.brand = brand

            class Car:
                colour: str
                engine = Engine()
                engine_class = None
                other_none_var = None

                def __init__(self, colour: str) -> str:
                    self.colour = colour

            class Carwash:
                car_a = Car("red")
                car_b = Car("blue")

                def __init__(self) -> str:
                    self.car_c = Car("green")
            """
        )

        module.load()
        old_engine_class = module.device.Engine

        module.rewrite(
            """
            class Engine:
                brand: str

                def __init__(self, brand: str = "Tesla"):
                    self.brand = brand

            class Car:
                colour: str
                engine = Engine("BMW")
                engine_class = Engine
                other_none_var = None

                def __init__(self, colour: str) -> str:
                    self.colour = colour

            class Carwash:
                car_a = Car("yellow")
                car_b = Car("blue")

                def __init__(self) -> str:
                    self.car_c = Car("black")
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Update: ClassVariable: module.Car.engine",
                "Update: ClassVariable: module.Car.engine_class",
                "Update: ClassVariable: module.Carwash.car_a",
                "Update: Method: module.Carwash.__init__",
        )

        assert module.device.Engine is old_engine_class
        assert isinstance(module.device.Carwash().car_b, module.device.Car)
        assert isinstance(module.device.Carwash().car_c, module.device.Car)
        assert isinstance(module.device.Carwash().car_a, module.device.Car)
        assert isinstance(module.device.Carwash().car_a.engine, module.device.Engine)
        assert module.device.Car.engine_class is module.device.Engine
        assert module.device.Carwash().car_a.engine_class is module.device.Engine

    def test_modified_property(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                @property
                def sprinklers_n(self) -> str:
                    return 3

                @property
                def cars_n(self) -> str:
                    return 5
            """
        )

        module.load()
        assert module.device.Carwash().sprinklers_n == 3
        assert module.device.Carwash().cars_n == 5

        module.rewrite(
                """
            class Carwash:
                @property
                def sprinklers_n(self) -> str:
                    return 10

                @property
                def cars_n(self) -> str:
                    return 5
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Update: PropertyGetter: module.Carwash.sprinklers_n",
        )

        assert module.device.Carwash().sprinklers_n == 10
        assert module.device.Carwash().cars_n == 5

    def test_modified_property_setter(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                @property
                def sprinklers_n(self) -> str:
                    return 10

                @sprinklers_n.setter
                def sprinklers_n(self, x) -> str:
                    self.a = x
            """
        )

        module.load()
        assert module.device.Carwash().sprinklers_n == 10

        module.replace("self.a = x", "self.a = x + 1")

        reloader = Reloader(sandbox,)
        reloader.reload(module)

        reloader.assert_actions(
                "Update: Module: module",
                "Update: PropertySetter: module.Carwash.sprinklers_n__setter__"
        )

        assert module.device.Carwash().sprinklers_n == 10

    def test_added_method(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                pass
            """
        )

        module.load()

        module.rewrite(
                """
            class Carwash:
                def print_sprinklers(self) -> str:
                    return f"There are 5 sprinklers."
            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module", "Add: Method: module.Carwash.print_sprinklers"
        )

        assert module.device.Carwash().print_sprinklers() == "There are 5 sprinklers."

    def test_delete_method(self, sandbox):
        module = Module("module.py",
                """
            class Carwash:
                def fun1(self):
                    return 2

                def fun2(self):
                    return 4
            """
        )

        module.load()

        assert hasattr(module.device.Carwash, "fun1")
        assert hasattr(module.device.Carwash, "fun2")

        module.rewrite(
                """
            class Carwash:
                def fun1(self):
                    return 2

            """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Delete: Method: module.Carwash.fun2")

        assert hasattr(module.device.Carwash, "fun1")
        assert not hasattr(module.device.Carwash, "fun2")
