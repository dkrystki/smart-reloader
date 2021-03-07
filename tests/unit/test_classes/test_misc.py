from pytest import raises

from smartreloader import FullReloadNeeded
from tests import utils
from tests.utils import Module, MockedPartialReloader


class TestClasses(utils.TestBase):
    def test_modified_class_variable_with_dependencies(self, sandbox):
        reloader = MockedPartialReloader(sandbox.parent)

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
        import math

        class Carwash:
            sprinkler_n = 3
        """,
        )

        car = Module(
            "car.py",
            """
        import math
        from .carwash import Carwash

        class Car: 
            car_sprinklers = Carwash.sprinkler_n / 3
        """,
        )

        init.load()

        carwash.load_from(init)
        car.load_from(init)
        reloader.assert_objects(carwash, 'sandbox.carwash.math: Import',
                                         'sandbox.carwash.Carwash: Class',
                                         'sandbox.carwash.Carwash.sprinkler_n: ClassVariable')
        reloader.assert_objects(init, 'sandbox.carwash: Import', 'sandbox.car: Import')

        assert carwash.device.Carwash.sprinkler_n == 3
        assert car.device.Car.car_sprinklers == 1

        carwash.replace("sprinkler_n = 3", "sprinkler_n = 6")

        reloader.reload(carwash)
        reloader.assert_objects(carwash, 'sandbox.carwash.math: Import',
                                         'sandbox.carwash.Carwash: Class',
                                         'sandbox.carwash.Carwash.sprinkler_n: ClassVariable')
        reloader.assert_objects(init, 'sandbox.carwash: Import', 'sandbox.car: Import')

        reloader.assert_actions(
            "Update Module: sandbox.carwash",
            "Update ClassVariable: sandbox.carwash.Carwash.sprinkler_n",
            "Update Module: sandbox.car",
            "Update ClassVariable: sandbox.car.Car.car_sprinklers",
        )

        assert carwash.device.Carwash.sprinkler_n == 6
        assert car.device.Car.car_sprinklers == 2

        reloader.rollback()
        init.assert_not_changed()
        carwash.assert_not_changed()
        car.assert_not_changed()

    def test_modified_class_attr(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
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
        """,
        )

        module.load()
        reloader.assert_objects(module, 'module.math: Import',
                                        'module.CarwashBase: Class',
                                        'module.CarwashBase.sprinklers_n: ClassVariable',
                                        'module.CarwashBase.print_sprinklers: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.sprinklers_n: ClassVariable',
                                        'module.Carwash.print_sprinklers: Method')

        print_sprinklers_id = id(module.device.CarwashBase.print_sprinklers)

        def assert_not_reloaded():
            assert print_sprinklers_id == id(module.device.CarwashBase.print_sprinklers)

        assert_not_reloaded()

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

        reloader.reload(module)
        reloader.assert_objects(module, 'module.math: Import',
                                        'module.CarwashBase: Class',
                                        'module.CarwashBase.sprinklers_n: ClassVariable',
                                        'module.CarwashBase.print_sprinklers: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.sprinklers_n: ClassVariable',
                                        'module.Carwash.print_sprinklers: Method')

        reloader.assert_actions(
            "Update Module: module",
            "Update ClassVariable: module.CarwashBase.sprinklers_n",
            "Update ClassVariable: module.Carwash.sprinklers_n",
        )

        assert module.device.CarwashBase.sprinklers_n == 55
        assert module.device.Carwash.sprinklers_n == 77
        assert print_sprinklers_id == id(module.device.CarwashBase.print_sprinklers)

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_add_init_with_super(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash(CarwashBase):
            pass
        """,
        )

        module.load()
        reloader.assert_objects(module, 'module.CarwashBase: Class',
                                        'module.CarwashBase.__init__: Method',
                                        'module.Carwash: Class')

        base_init_id = id(module.device.CarwashBase.__init__)

        def assert_correnct_ids():
            assert base_init_id == id(module.device.CarwashBase.__init__)
        assert_correnct_ids()

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

        reloader.reload(module)
        reloader.assert_objects(module, 'module.CarwashBase: Class',
                                        'module.CarwashBase.__init__: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.__init__: Method')
        reloader.assert_actions(
            "Update Module: module", "Add Method: module.Carwash.__init__"
        )

        assert module.device.Carwash(30).car_n == 30
        assert base_init_id == id(module.device.CarwashBase.__init__)

        assert_correnct_ids()

        reloader.rollback()
        assert_correnct_ids()
        module.assert_not_changed()

    def test_modified_init_with_super(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash(CarwashBase):
            def __init__(self, car_n: int) -> None:
                self.car_n = car_n
        """,
        )

        module.load()
        reloader.assert_objects(module, 'module.CarwashBase: Class',
                                        'module.CarwashBase.__init__: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.__init__: Method')

        base_init_id = id(module.device.CarwashBase.__init__)
        init_id = id(module.device.Carwash.__init__)

        def assert_correct_ids():
            assert base_init_id == id(module.device.CarwashBase.__init__)
            assert init_id == id(module.device.Carwash.__init__)
        assert_correct_ids()

        module.rewrite(
            """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash(CarwashBase):
            def __init__(self, car_n: int) -> None:
                super().__init__()
                self.car_n = car_n + 10
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.CarwashBase: Class',
                                        'module.CarwashBase.__init__: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.__init__: Method')
        reloader.assert_actions(
            "Update Module: module", "Update Method: module.Carwash.__init__"
        )

        assert module.device.Carwash(30).car_n == 40
        assert_correct_ids()

        reloader.rollback()

        assert_correct_ids()
        assert module.device.Carwash(30).car_n == 30

        module.assert_not_changed()

    def test_add_base_class(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class CarwashBase:
            def __init__(self) -> None:
                self.car_n = 10

        class Carwash:
            def __init__(self, car_n: int) -> None:
                self.car_n = car_n
        """,
        )

        module.load()
        reloader.assert_objects(module, 'module.CarwashBase: Class',
                                        'module.CarwashBase.__init__: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.__init__: Method')

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

        with raises(FullReloadNeeded):
            reloader.reload(module)

        reloader.assert_objects(module, 'module.CarwashBase: Class',
                                        'module.CarwashBase.__init__: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.__init__: Method')

        module.assert_not_changed()

    def test_type_as_attribute(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Carwash:
            name_type = int
        """,
        )

        module.load()
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.name_type: ClassVariable')

        def assert_not_reloaded():
            assert module.device.Carwash.name_type is int

        assert_not_reloaded()

        module.replace("name_type = int", "name_type = str")

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.name_type: ClassVariable')
        reloader.assert_actions(
            "Update Module: module", "Update ClassVariable: module.Carwash.name_type"
        )

        assert module.device.Carwash.name_type is str
        reloader.rollback()
        module.assert_not_changed()
        assert_not_reloaded()

    def test_added_class(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        a = 1
        """
        )

        module.load()
        reloader.assert_objects(module, 'module.a: Variable')

        module.rewrite(
            """
        a = 1

        class Carwash:
            sprinklers_n: int = 55

            def print_sprinklers(self) -> str:
                return 20
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.a: Variable',
                                        'module.Carwash: Class',
                                        'module.Carwash.sprinklers_n: ClassVariable',
                                        'module.Carwash.print_sprinklers: Method')
        reloader.assert_actions("Update Module: module", "Add Class: module.Carwash")

        assert module.device.Carwash.sprinklers_n == 55
        assert module.device.Carwash().print_sprinklers() == 20

        reloader.rollback()
        module.assert_not_changed()

    def test_recursion(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Carwash:
            class_attr = 2

        Carwash.klass = Carwash 
        """
        )

        module.load()
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.class_attr: ClassVariable')

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.class_attr: ClassVariable')
        module.assert_not_changed()

    def test_recursion_two_deep(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Carwash:
            class_attr = 2

            class Car:
                class_attr2 = 13

        Carwash.Car.klass = Carwash 
        """
        )

        module.load()
        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.class_attr: ClassVariable',
                                        'module.Carwash.Car: Class',
                                        'module.Carwash.Car.class_attr2: ClassVariable')
        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.class_attr: ClassVariable',
                                        'module.Carwash.Car: Class',
                                        'module.Carwash.Car.class_attr2: ClassVariable')
        module.assert_not_changed()

    def test_added_class_attr(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                sprinklers_n: int = 22

                def fun(self) -> str:
                    return 12
            """
        )

        module.load()
        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.sprinklers_n: ClassVariable',
                                            'module.Carwash.fun: Method')
            assert hasattr(module.device.Carwash, "sprinklers_n")
            assert not hasattr(module.device.Carwash, "cars_n")

        assert_not_reloaded()

        module.rewrite(
            """
        class Carwash:
            sprinklers_n: int = 22
            cars_n: int = 15

            def fun(self) -> str:
                return 12
        """
        )

        reloader.reload(module)

        reloader.assert_actions('Update Module: module',
                                'Add ClassVariable: module.Carwash.cars_n',
                                'Move Method: module.Carwash.fun')

        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.sprinklers_n: ClassVariable',
                                        'module.Carwash.cars_n: ClassVariable',
                                        'module.Carwash.fun: Method')

        assert hasattr(module.device.Carwash, "sprinklers_n")
        assert hasattr(module.device.Carwash, "cars_n")

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_deleted_class_attr(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                sprinklers_n: int = 22
                cars_n: int = 15

                def fun(self) -> str:
                    return 12
            """
        )

        module.load()
        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.sprinklers_n: ClassVariable',
                                            'module.Carwash.cars_n: ClassVariable',
                                            'module.Carwash.fun: Method')

            assert hasattr(module.device.Carwash, "sprinklers_n")
            assert hasattr(module.device.Carwash, "cars_n")
        assert_not_reloaded()

        # First edit
        module.rewrite(
            """
            class Carwash:
                sprinklers_n: int = 22

                def fun(self) -> str:
                    return 12
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.sprinklers_n: ClassVariable',
                                        'module.Carwash.fun: Method')

        reloader.assert_actions('Update Module: module',
                             'Delete ClassVariable: module.Carwash.cars_n',
                             'Move Method: module.Carwash.fun')

        assert hasattr(module.device.Carwash, "sprinklers_n")
        assert not hasattr(module.device.Carwash, "cars_n")

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_modified_classmethod(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                @classmethod
                def print_sprinklers_cls(cls) -> str:
                    return f"There is one sprinkler (Cls)."

                def print_sprinklers(self) -> str:
                    return f"There is one sprinkler."
            """,
        )

        module.load()

        reffered_print_sprinklers_cls = module.device.Carwash.print_sprinklers_cls
        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.print_sprinklers_cls: ClassMethod',
                                            'module.Carwash.print_sprinklers: Method')

            assert (
                module.device.Carwash.print_sprinklers_cls()
                == "There is one sprinkler (Cls)."
            )
            assert reffered_print_sprinklers_cls() == "There is one sprinkler (Cls)."
            assert module.device.Carwash().print_sprinklers() == "There is one sprinkler."

        assert_not_reloaded()

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

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.print_sprinklers_cls: ClassMethod',
                                        'module.Carwash.print_sprinklers: Method')

        reloader.assert_actions(
            "Update Module: module",
            "Update ClassMethod: module.Carwash.print_sprinklers_cls",
            "Update Method: module.Carwash.print_sprinklers",
        )

        assert (
            module.device.Carwash.print_sprinklers_cls()
            == "There are 5 sprinklers (Cls)."
        )
        assert reffered_print_sprinklers_cls() == "There are 5 sprinklers (Cls)."
        assert module.device.Carwash().print_sprinklers() == "There are 5 sprinklers."
        assert print_sprinklers_id == id(module.device.Carwash.print_sprinklers)

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_modified_repr(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                def __repr__(self) -> str:
                    return "Carwash"
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.__repr__: Method')
            assert repr(module.device.Carwash()) == "Carwash"
        assert_not_reloaded()

        module.rewrite(
            """
            class Carwash:
                def __repr__(self) -> str:
                    return "MyCarwash"
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.__repr__: Method')

        reloader.assert_actions(
            "Update Module: module", "Update Method: module.Carwash.__repr__"
        )

        assert repr(module.device.Carwash()) == "MyCarwash"

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_uses_other_classes(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
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
            """,
        )

        module.load()

        old_engine_class = module.device.Engine

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Engine: Class',
                                            'module.Engine.__init__: Method',
                                            'module.Car: Class',
                                            'module.Car.engine: ClassVariable',
                                            'module.Car.engine_class: ClassVariable',
                                            'module.Car.other_none_var: ClassVariable',
                                            'module.Car.__init__: Method',
                                            'module.Carwash: Class',
                                            'module.Carwash.car_a: ClassVariable',
                                            'module.Carwash.car_b: ClassVariable',
                                            'module.Carwash.__init__: Method')

            assert module.device.Engine is old_engine_class
        assert_not_reloaded()

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

        reloader.reload(module)

        reloader.assert_actions(
            "Update Module: module",
            "Update ClassVariable: module.Car.engine",
            "Update ClassVariable: module.Car.engine_class",
            "Update ClassVariable: module.Carwash.car_a",
            "Update Method: module.Carwash.__init__",
        )

        reloader.assert_objects(module, 'module.Engine: Class',
                                        'module.Engine.__init__: Method',
                                        'module.Car: Class',
                                        'module.Car.engine: ClassVariable',
                                        'module.Car.engine_class: Reference',
                                        'module.Car.other_none_var: ClassVariable',
                                        'module.Car.__init__: Method',
                                        'module.Carwash: Class',
                                        'module.Carwash.car_a: ClassVariable',
                                        'module.Carwash.car_b: ClassVariable',
                                        'module.Carwash.__init__: Method')

        assert module.device.Engine is old_engine_class
        assert isinstance(module.device.Carwash().car_b, module.device.Car)
        assert isinstance(module.device.Carwash().car_c, module.device.Car)
        assert isinstance(module.device.Carwash().car_a, module.device.Car)
        assert isinstance(module.device.Carwash().car_a.engine, module.device.Engine)
        assert module.device.Car.engine_class is module.device.Engine
        assert module.device.Carwash().car_a.engine_class is module.device.Engine

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_modified_property(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                @property
                def sprinklers_n(self) -> str:
                    return 3

                @property
                def cars_n(self) -> str:
                    return 5
            """,
        )

        module.load()
        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.sprinklers_n: PropertyGetter',
                                            'module.Carwash.cars_n: PropertyGetter')
            assert module.device.Carwash().sprinklers_n == 3
            assert module.device.Carwash().cars_n == 5

        assert_not_reloaded()

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

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.sprinklers_n: PropertyGetter',
                                        'module.Carwash.cars_n: PropertyGetter')
        reloader.assert_actions('Update Module: module', 'Update PropertyGetter: module.Carwash.sprinklers_n')

        assert module.device.Carwash().sprinklers_n == 10
        assert module.device.Carwash().cars_n == 5

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_modified_property_setter(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                @property
                def sprinklers_n(self) -> str:
                    return 10

                @sprinklers_n.setter
                def sprinklers_n(self, x) -> str:
                    self.a = x
            """,
        )

        module.load()
        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.sprinklers_n: PropertyGetter',
                                            'module.Carwash.sprinklers_n__setter__: PropertySetter')
            assert module.device.Carwash().sprinklers_n == 10
        assert_not_reloaded()

        module.replace("self.a = x", "self.a = x + 1")

        reloader.reload(module)

        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.sprinklers_n: PropertyGetter',
                                        'module.Carwash.sprinklers_n__setter__: PropertySetter')

        assert module.device.Carwash().sprinklers_n == 10

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_added_method(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                pass
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class')

        assert_not_reloaded()

        module.rewrite(
            """
            class Carwash:
                def print_sprinklers(self) -> str:
                    return f"There are 5 sprinklers."
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.print_sprinklers: Method')
        reloader.assert_actions(
            "Update Module: module", "Add Method: module.Carwash.print_sprinklers"
        )

        assert module.device.Carwash().print_sprinklers() == "There are 5 sprinklers."

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_delete_method(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Carwash:
                def fun1(self):
                    return 2

                def fun2(self):
                    return 4
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.fun1: Method',
                                            'module.Carwash.fun2: Method')
            assert hasattr(module.device.Carwash, "fun1")
            assert hasattr(module.device.Carwash, "fun2")

        assert_not_reloaded()

        module.rewrite(
            """
            class Carwash:
                def fun1(self):
                    return 2

            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.fun1: Method')

        reloader.assert_actions(
            "Update Module: module", "Delete Method: module.Carwash.fun2"
        )

        assert hasattr(module.device.Carwash, "fun1")
        assert not hasattr(module.device.Carwash, "fun2")

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_edit_method_with_inheritance(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class CarwashBase:
                def fun(self):
                    return 2
            
            class Carwash(CarwashBase):
                pass
            """,
        )

        module.load()
        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.CarwashBase: Class',
                                            'module.CarwashBase.fun: Method',
                                            'module.Carwash: Class')
            assert module.device.CarwashBase().fun() == 2
            assert module.device.Carwash().fun() == 2

        assert_not_reloaded()

        module.replace("return 2", "return 10")

        reloader.reload(module)
        reloader.assert_objects(module, 'module.CarwashBase: Class',
                                        'module.CarwashBase.fun: Method',
                                        'module.Carwash: Class')

        reloader.assert_actions('Update Module: module', 'Update Method: module.CarwashBase.fun')

        assert module.device.CarwashBase().fun() == 10
        assert module.device.Carwash().fun() == 10

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_add_nested(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Carwash:
            name: str = "carwash"
        """,
        )

        module.load()

        def assert_not_reloaded():
            assert not hasattr(module.device.Carwash, "Meta")
            reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.name: ClassVariable')

        assert_not_reloaded()

        module.rewrite(
            """
        class Carwash:
            class Meta:
                car_numbers: int = 5
            
            name: str = "carwash"
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.Meta: Class',
                                        'module.Carwash.Meta.car_numbers: ClassVariable',
                                        'module.Carwash.name: ClassVariable')

        reloader.assert_actions(
            "Update Module: module", "Add Class: module.Carwash.Meta"
        )
        assert hasattr(module.device.Carwash, "Meta")

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_modify_nested(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Carwash:
            class Meta:
                car_numbers: int = 5
            
            name: str = "carwash"
        """,
        )

        module.load()

        carwash_class_id = id(module.device.Carwash)
        carwash_meta_class_id = id(module.device.Carwash.Meta)

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.Meta: Class',
                                            'module.Carwash.Meta.car_numbers: ClassVariable',
                                            'module.Carwash.name: ClassVariable')

        def assert_id_not_changed():
            assert id(module.device.Carwash) == carwash_class_id
            assert id(module.device.Carwash.Meta) == carwash_meta_class_id

        assert_not_reloaded()
        assert_id_not_changed()

        module.rewrite(
            """
        class Carwash:
            class Meta:
                car_numbers: int = 15

            name: str = "carwash"
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class',
                                        'module.Carwash.Meta: Class',
                                        'module.Carwash.Meta.car_numbers: ClassVariable',
                                        'module.Carwash.name: ClassVariable')
        assert_id_not_changed()
        reloader.assert_actions(
            "Update Module: module",
            "Update ClassVariable: module.Carwash.Meta.car_numbers",
        )


        reloader.rollback()
        assert_not_reloaded()
        assert_id_not_changed()
        module.assert_not_changed()

    def test_delete_nested(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Carwash:
            class Meta:
                car_numbers: int = 5

            name: str = "carwash"
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Carwash: Class',
                                            'module.Carwash.Meta: Class',
                                            'module.Carwash.Meta.car_numbers: ClassVariable',
                                            'module.Carwash.name: ClassVariable')
            assert hasattr(module.device.Carwash, "Meta")

        assert_not_reloaded()

        module.rewrite(
            """
        class Carwash:
            name: str = "carwash"
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Carwash: Class', 'module.Carwash.name: ClassVariable')

        reloader.assert_actions(
            "Update Module: module", "Delete Class: module.Carwash.Meta"
        )

        assert not hasattr(module.device.Carwash, "Meta")

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_class_changed_to_reference(self, sandbox):
        reloader = MockedPartialReloader(sandbox.parent)

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
        class CarNameType:
            a = 1
        
        class Carwash:
            name_type = CarNameType
        """,
        )

        car = Module(
            "car.py",
            """
        from .carwash import Carwash
        
        class SuperCarwash(Carwash): 
            pass
        """,
        )

        init.load()
        carwash.load_from(init)
        car.load_from(init)

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.carwash: Import', 'sandbox.car: Import')
            reloader.assert_objects(carwash, 'sandbox.carwash.CarNameType: Class',
                                             'sandbox.carwash.CarNameType.a: ClassVariable',
                                             'sandbox.carwash.Carwash: Class',
                                             'sandbox.carwash.Carwash.name_type: Reference')
            reloader.assert_objects(car, 'sandbox.car.Carwash: Foreigner', 'sandbox.car.SuperCarwash: Class')

        assert_not_reloaded()

        car.rewrite(
            """
        from .carwash import Carwash
        
        class NameType:
            pass
        
        class SuperCarwash(Carwash): 
            name_type = NameType 
        """
        )

        reloader.reload(car)
        reloader.assert_objects(init, 'sandbox.carwash: Import', 'sandbox.car: Import')
        reloader.assert_objects(carwash, 'sandbox.carwash.CarNameType: Class',
                                         'sandbox.carwash.CarNameType.a: ClassVariable',
                                         'sandbox.carwash.Carwash: Class',
                                         'sandbox.carwash.Carwash.name_type: Reference')
        reloader.assert_objects(car, 'sandbox.car.Carwash: Foreigner',
                                     'sandbox.car.NameType: Class',
                                     'sandbox.car.SuperCarwash: Class',
                                     'sandbox.car.SuperCarwash.name_type: Reference')

        reloader.assert_actions(
            "Update Module: sandbox.car",
            "Add Class: sandbox.car.NameType",
            "Add Reference: sandbox.car.SuperCarwash.name_type",
        )
        assert car.device.SuperCarwash.name_type is car.device.NameType

        reloader.rollback()
        assert_not_reloaded()
        init.assert_not_changed()
        carwash.assert_not_changed()
        car.assert_not_changed()

    def test_only_reloads_user_defined(self, sandbox):
        reloader = MockedPartialReloader(sandbox.parent)

        init = Module(
            "__init__.py",
            """
        from . import cupcake
        """,
        )

        cupcake_base = Module(
            "cupcake_base.py",
            """
        class CupcakeBase:
            size = 10
        """,
        )

        cupcake = Module(
            "cupcake.py",
            """
        from .cupcake_base import CupcakeBase
        
        class Cupcake(CupcakeBase): 
            colour = "red"
        """
        )

        init.load()
        cupcake_base.load_from(init)
        cupcake.load_from(init)

        def assert_not_reloaded():
            reloader.assert_objects(init, 'sandbox.cupcake_base: Import', 'sandbox.cupcake: Import')
            reloader.assert_objects(cupcake_base, 'sandbox.cupcake_base.CupcakeBase: Class',
                                                  'sandbox.cupcake_base.CupcakeBase.size: ClassVariable')
            reloader.assert_objects(cupcake, 'sandbox.cupcake.CupcakeBase: Foreigner',
                                             'sandbox.cupcake.Cupcake: Class',
                                             'sandbox.cupcake.Cupcake.colour: ClassVariable')
        assert_not_reloaded()

        cupcake.device.Cupcake.size = 15

        reloader.reload(cupcake)
        assert_not_reloaded()
        reloader.assert_actions('Update Module: sandbox.cupcake')

    def test_method_with_list_comprehensions_twice(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Cupcake:
            def eat(self):
                a = [i for i in range(10)]
    
                return 10
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cupcake: Class', 'module.Cupcake.eat: Method')
            assert module.device.Cupcake().eat() == 10

        assert_not_reloaded()

        module.rewrite(
            """
        class Cupcake:
            def eat(self):
                a = [i for i in range(10)]
    
                return 12
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class', 'module.Cupcake.eat: Method')
        reloader.assert_actions(
            'Update Module: module', 'Update Method: module.Cupcake.eat',
        )

        reloader.reload(module)
        reloader.assert_actions(
            'Update Module: module',
        )

    def test_method_not_changed_should_not_reload(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Cupcake:
            def eat(self):
                return 10
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cupcake: Class', 'module.Cupcake.eat: Method')

        module.rewrite(
            """
        class Cupcake:
            def eat(self):
                return 10
        """
        )

        reloader.reload(module)
        assert_not_reloaded()
        reloader.assert_actions('Update Module: module')

        reloader.reload(module)
        assert_not_reloaded()
        reloader.assert_actions('Update Module: module')

    def test_add_method_closure(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Cupcake:
                def eat(self):
                    return "Eating"
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cupcake: Class', 'module.Cupcake.eat: Method')

        assert_not_reloaded()

        module.rewrite(
            """
            class Cupcake:
                def eat(self):
                    def sweet():
                        return "very sweet"
                    return f"Eating {sweet()} cupcake"
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class', 'module.Cupcake.eat: Method')

        reloader.assert_actions('Update Module: module', 'Update Method: module.Cupcake.eat')

        assert module.device.Cupcake().eat() == "Eating very sweet cupcake"

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_edit_method_closure(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Cupcake:
                def eat(self):
                    def sweet():
                        return "very sweet"
                    return f"Eating {sweet()} cupcake"
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cupcake: Class', 'module.Cupcake.eat: Method')

        assert_not_reloaded()

        module.rewrite(
            """
            class Cupcake:
                def eat(self):
                    def sweet():
                        return "super sweet"
                    return f"Eating {sweet()} cupcake"
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class', 'module.Cupcake.eat: Method')

        reloader.assert_actions('Update Module: module', 'Update Method: module.Cupcake.eat')

        assert module.device.Cupcake().eat() == "Eating super sweet cupcake"

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_add_lambda(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Cake:
            pass
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cake: Class')

        assert_not_reloaded()

        module.rewrite(
            """
        class Cake:
            fun = lambda x: x * 5
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cake: Class', 'module.Cake.fun: Method')

        reloader.assert_actions('Update Module: module', 'Add Method: module.Cake.fun')
        assert module.device.Cake.fun(5) == 25

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_edit_lambda(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Cake:
            fun = lambda x: x * 3
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cake: Class', 'module.Cake.fun: Method')

        assert_not_reloaded()

        module.rewrite(
            """
        class Cake:
            fun = lambda x: x * 5
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cake: Class', 'module.Cake.fun: Method')

        reloader.assert_actions('Update Module: module', 'Update Method: module.Cake.fun')
        assert module.device.Cake.fun(5) == 25

        reloader.rollback()
        module.assert_not_changed()
        assert_not_reloaded()

        assert module.device.Cake.fun(5) == 15

    def test_add_staticmethod(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Cake:
            pass
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cake: Class')

        assert_not_reloaded()

        module.rewrite(
            """
        class Cake:
            @staticmethod
            def eat():
                return "Eating"
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cake: Class', 'module.Cake.eat: StaticMethod')

        reloader.assert_actions('Update Module: module', 'Add StaticMethod: module.Cake.eat')
        assert module.device.Cake.eat() == "Eating"

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_edit_staticmethod(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Cake:
            @staticmethod
            def eat():
                return "Eating"
        """,
        )

        module.load()
        eat_id = id(module.device.Cake.eat)

        def assert_ids():
            assert id(module.device.Cake.eat) == eat_id

        def assert_not_reloaded():
            assert_ids()
            reloader.assert_objects(module, 'module.Cake: Class', 'module.Cake.eat: StaticMethod')

        assert_not_reloaded()

        module.rewrite(
            """
        class Cake:
            @staticmethod
            def eat():
                return "Eating fast"
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cake: Class', 'module.Cake.eat: StaticMethod')
        assert_ids()

        reloader.assert_actions('Update Module: module', 'Update StaticMethod: module.Cake.eat')
        assert module.device.Cake.eat() == "Eating fast"

        reloader.rollback()
        module.assert_not_changed()

        assert module.device.Cake.eat() == "Eating"

    def test_import_external_class(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        from typing import List, Dict
        
        test_type = List
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.List: Foreigner',
                                            'module.Dict: Foreigner',
                                            'module.test_type: Reference')
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
        from typing import List, Dict
        
        test_type = Dict
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.List: Foreigner',
                                        'module.Dict: Foreigner',
                                        'module.test_type: Reference')

        reloader.assert_actions('Update Module: module', 'Update Reference: module.test_type')

        reloader.rollback()
        assert_not_reloaded()

    def test_moves_functions_first_lines_class_methods(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Cupcake:
                def eat(self):
                    return f"Eating 1 cupcake"
                
                @classmethod
                def name(self):
                    return "Cupcake"
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cupcake: Class',
                                            'module.Cupcake.eat: Method',
                                            'module.Cupcake.name: ClassMethod')
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
            class Cupcake:
            
                def eat(self):
                    return f"Eating 1 cupcake"
                
                @classmethod
                def name(self):
                    return "Cupcake"
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.eat: Method',
                                        'module.Cupcake.name: ClassMethod')

        reloader.assert_actions('Update Module: module',
                                'Move Method: module.Cupcake.eat',
                                'Move ClassMethod: module.Cupcake.name')

        assert module.device.Cupcake.eat.__code__.co_firstlineno == 4
        assert module.device.Cupcake.name.__func__.__code__.co_firstlineno == 7

        reloader.rollback()
        assert module.device.Cupcake.eat.__code__.co_firstlineno == 4
        assert module.device.Cupcake.name.__func__.__code__.co_firstlineno == 7

        assert_not_reloaded()
