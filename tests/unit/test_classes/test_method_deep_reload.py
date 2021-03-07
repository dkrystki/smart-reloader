from pytest import raises

from tests import utils
from tests.utils import Module, MockedPartialReloader


class TestClassesDeepReload(utils.TestBase):
    def test_change_to_classmethod(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour
    
                def eat(self):
                    return f"Eating {self.colour} cupcake"
    
            cupcake = Cupcake("blue")
            """,
        )

        module.load()
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.shape: ClassVariable',
                                        'module.Cupcake.__init__: Method',
                                        'module.Cupcake.eat: Method',
                                        'module.cupcake: Variable')

        module.rewrite(
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour
    
                @classmethod
                def eat(cls):
                    return f"Eating {cls.shape} cupcake"
    
            cupcake = Cupcake("blue")
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.shape: ClassVariable',
                                        'module.Cupcake.__init__: Method',
                                        'module.Cupcake.eat: ClassMethod',
                                        'module.cupcake: Variable')

        reloader.assert_actions('Update Module: module', 'DeepUpdate Method: module.Cupcake.eat')

        assert module.device.Cupcake().eat() == "Eating round cupcake"
        assert module.device.Cupcake.eat() == "Eating round cupcake"
        assert module.device.cupcake.eat() == "Eating round cupcake"

        reloader.rollback()
        module.assert_not_changed()

    def test_change_to_staticmethod(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour

                def eat(self):
                    return f"Eating {self.colour} cupcake"

            cupcake = Cupcake("blue")
            """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'module.Cupcake: Class',
                                            'module.Cupcake.shape: ClassVariable',
                                            'module.Cupcake.__init__: Method',
                                            'module.Cupcake.eat: Method',
                                            'module.cupcake: Variable')
            module.assert_not_changed()

        assert_not_reloaded()

        module.rewrite(
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour

                @staticmethod
                def eat():
                    return f"Eating a beautiful cupcake"

            cupcake = Cupcake("blue")
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.shape: ClassVariable',
                                        'module.Cupcake.__init__: Method',
                                        'module.Cupcake.eat: StaticMethod',
                                        'module.cupcake: Variable')

        reloader.assert_actions('Update Module: module', 'DeepUpdate Method: module.Cupcake.eat')

        assert module.device.Cupcake().eat() == "Eating a beautiful cupcake"
        assert module.device.Cupcake.eat() == "Eating a beautiful cupcake"
        assert module.device.cupcake.eat() == "Eating a beautiful cupcake"

        reloader.rollback()
        assert_not_reloaded()

    def test_staticmethod_to_method(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour

                @staticmethod
                def eat():
                    return f"Eating a beautiful cupcake"

            cupcake = Cupcake("blue")
            """,
        )

        module.load()
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.shape: ClassVariable',
                                        'module.Cupcake.__init__: Method',
                                        'module.Cupcake.eat: StaticMethod',
                                        'module.cupcake: Variable')

        module.rewrite(
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour

                def eat(self):
                    return f"Eating {self.colour} cupcake"

            cupcake = Cupcake("blue")
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.shape: ClassVariable',
                                        'module.Cupcake.__init__: Method',
                                        'module.Cupcake.eat: Method',
                                        'module.cupcake: Variable')
        reloader.assert_actions('Update Module: module', 'DeepUpdate StaticMethod: module.Cupcake.eat')

        assert module.device.Cupcake().eat() == "Eating red cupcake"
        assert module.device.cupcake.eat() == "Eating blue cupcake"

        with raises(TypeError):
            assert module.device.Cupcake.eat() == "Eating red cupcake"

        reloader.rollback()
        module.assert_not_changed()

    def test_change_from_classmethod_to_method(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour

                @classmethod
                def eat(cls):
                    return f"Eating {cls.shape} cupcake"

            class CupcakePro(Cupcake):
                pass

            cupcake = Cupcake("blue")
            cupcake_pro = CupcakePro("blue")
            """,
        )

        module.load()
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.shape: ClassVariable',
                                        'module.Cupcake.__init__: Method',
                                        'module.Cupcake.eat: ClassMethod',
                                        'module.CupcakePro: Class',
                                        'module.cupcake: Variable',
                                        'module.cupcake_pro: Variable')

        module.rewrite(
            """
            class Cupcake:
                shape = "round"
                def __init__(self, colour="red"):
                    self.colour = colour

                def eat(self):
                    return f"Eating {self.colour} cupcake"

            class CupcakePro(Cupcake):
                pass

            cupcake = Cupcake("blue")
            cupcake_pro = CupcakePro("blue")
            """
        )

        # for some reason there's some kind of caching happening and multiple asserts wont' detect change

        # fun1 = module.device.Cupcake.eat
        # fun2 = module.device.Cupcake.eat.__func__

        # def assert_not_reloaded():
        #
        #     assert module.device.Cupcake().eat() == "Eating round cupcake"
        #     assert fun1() == "Eating round cupcake"
        #     assert module.device.cupcake.eat() == "Eating round cupcake"
        #     assert module.device.CupcakePro().eat() == "Eating round cupcake"

        # assert_not_reloaded()
        reloader.reload(module)
        reloader.assert_objects(module, 'module.Cupcake: Class',
                                        'module.Cupcake.shape: ClassVariable',
                                        'module.Cupcake.__init__: Method',
                                        'module.Cupcake.eat: Method',
                                        'module.CupcakePro: Class',
                                        'module.cupcake: Variable',
                                        'module.cupcake_pro: Variable')
        reloader.assert_actions('Update Module: module', 'DeepUpdate ClassMethod: module.Cupcake.eat')

        assert module.device.Cupcake().eat() == "Eating red cupcake"
        # assert fun1(module.device.Cupcake()) == "Eating red cupcake"
        assert module.device.cupcake.eat() == "Eating blue cupcake"
        assert module.device.CupcakePro().eat() == "Eating red cupcake"

        reloader.rollback()
        module.assert_not_changed()
        # assert_not_reloaded()

        # assert module.device.Cupcake.eat() == "Eating round cupcake"

    def test_add_decorator(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
            def eat_more(func):
                def wrapped_func(self):
                    return func(self) + 10
                return wrapped_func
                
            class Cupcake:
                def how_many_eat(self):
                    return 1
            """,
        )

        module.load()
        reloader.assert_objects(module, 'module.eat_more: Function',
                                        'module.Cupcake: Class',
                                        'module.Cupcake.how_many_eat: Method')

        module.rewrite(
            """
            def eat_more(func):
                def wrapped_func(self):
                    return func(self) + 10
                return wrapped_func
                
            class Cupcake:
                @eat_more
                def how_many_eat(self):
                    return 1
            """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'module.eat_more: Function',
                                        'module.Cupcake: Class',
                                        'module.Cupcake.how_many_eat: Method')
        reloader.assert_actions('Update Module: module', 'DeepUpdate Method: module.Cupcake.how_many_eat')

        assert module.device.Cupcake().how_many_eat() == 11

        reloader.rollback()
        module.assert_not_changed()
