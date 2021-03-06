import pytest

from tests import utils
from tests.utils import Module, MockedPartialReloader


class TestLists(utils.TestBase):
    def test_basic(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        cakes = ["Cheesecake", "Chiffon Cake"]
        """,
        )

        module.load()

        cakes_id = id(module.device.cakes)

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.cakes: List', 'sandbox.module.cakes.0: Variable', 'sandbox.module.cakes.1: Variable')
            assert cakes_id == id(module.device.cakes)

        assert_not_reloaded()

        module.rewrite(
            """
        cakes = ["Cheesecake", "Chiffon Cake", "Black Forest Cake"]
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.cakes: List',
                                        'sandbox.module.cakes.0: Variable',
                                        'sandbox.module.cakes.1: Variable',
                                        'sandbox.module.cakes.2: Variable')

        reloader.assert_actions('Update Module: sandbox.module', 'Update List: sandbox.module.cakes')

        assert module.device.cakes == ["Cheesecake", "Chiffon Cake", "Black Forest Cake"]
        assert cakes_id == id(module.device.cakes)

        reloader.rollback()
        assert_not_reloaded()

    def test_nested(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        sweets = ["cheesecake", "Chiffon Cake", ["Cupcake", "Cookie"]]
        """,
        )

        module.load()

        sweets_id = id(module.device.sweets)
        nested_id = id(module.device.sweets[-1])

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.sweets: List',
                                            'sandbox.module.sweets.0: Variable',
                                            'sandbox.module.sweets.1: Variable',
                                            'sandbox.module.sweets.2: List',
                                            'sandbox.module.sweets.2.0: Variable',
                                            'sandbox.module.sweets.2.1: Variable')
            assert sweets_id == id(module.device.sweets)
            assert nested_id == id(module.device.sweets[-1])

        assert_not_reloaded()

        module.rewrite(
            """
        sweets = ["cheesecake", "Chiffon Cake", ["Cupcake", "Cookie", "Macaroon"]]
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.sweets: List',
                                        'sandbox.module.sweets.0: Variable',
                                        'sandbox.module.sweets.1: Variable',
                                        'sandbox.module.sweets.2: List',
                                        'sandbox.module.sweets.2.0: Variable',
                                        'sandbox.module.sweets.2.1: Variable',
                                        'sandbox.module.sweets.2.2: Variable')

        reloader.assert_actions('Update Module: sandbox.module', 'Update List: sandbox.module.sweets')

        assert module.device.sweets == ["cheesecake", "Chiffon Cake", ["Cupcake", "Cookie", "Macaroon"]]

        reloader.rollback()
        assert_not_reloaded()

    def test_fixes_references(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        class Cheesecake:
            pass
            
        class Cupcake:
            pass
            
        class ChiffonCake:
            pass
            
        class Cookie:
            pass
            
        class Macaroon:
            pass
        
        sweets = [Cheesecake, [Cupcake, Cookie]]
        """,
        )

        module.load()
        sweets_id = id(module.device.sweets)

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.Cheesecake: Class',
                                            'sandbox.module.Cupcake: Class',
                                            'sandbox.module.ChiffonCake: Class',
                                            'sandbox.module.Cookie: Class',
                                            'sandbox.module.Macaroon: Class',
                                            'sandbox.module.sweets: List',
                                            'sandbox.module.sweets.0: Reference',
                                            'sandbox.module.sweets.1: List',
                                            'sandbox.module.sweets.1.0: Reference',
                                            'sandbox.module.sweets.1.1: Reference')
            assert sweets_id == id(module.device.sweets)

        assert_not_reloaded()

        module.rewrite(
            """
        class Cheesecake:
            pass
            
        class Cupcake:
            pass
            
        class ChiffonCake:
            pass
            
        class Cookie:
            pass
            
        class Macaroon:
            pass
        
        sweets = [Cheesecake, ChiffonCake, [Cupcake, Cookie, Macaroon]]
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.Cheesecake: Class',
                                        'sandbox.module.Cupcake: Class',
                                        'sandbox.module.ChiffonCake: Class',
                                        'sandbox.module.Cookie: Class',
                                        'sandbox.module.Macaroon: Class',
                                        'sandbox.module.sweets: List',
                                        'sandbox.module.sweets.0: Reference',
                                        'sandbox.module.sweets.1: Reference',
                                        'sandbox.module.sweets.2: List',
                                        'sandbox.module.sweets.2.0: Reference',
                                        'sandbox.module.sweets.2.1: Reference',
                                        'sandbox.module.sweets.2.2: Reference')
        reloader.assert_actions('Update Module: sandbox.module', 'Update List: sandbox.module.sweets')

        assert module.device.sweets == [module.device.Cheesecake, module.device.ChiffonCake,
                                        [module.device.Cupcake, module.device.Cookie, module.device.Macaroon]]

        assert sweets_id == id(module.device.sweets)

        reloader.rollback()
        assert_not_reloaded()

    def test_tuples(self, sandbox, capsys):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        cakes = ("Cheesecake", "Chiffon Cake")
        
        class CakeShop:
            cakes_to_make = cakes
            
        """,
        )

        module.load()

        cakes_id = id(module.device.cakes)

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.cakes: Tuple',
                                            'sandbox.module.cakes.0: Variable',
                                            'sandbox.module.cakes.1: Variable',
                                            'sandbox.module.CakeShop: Class',
                                            'sandbox.module.CakeShop.cakes_to_make: Reference')
            assert cakes_id == id(module.device.cakes)

        assert_not_reloaded()

        module.rewrite(
            """
        cakes = ("Cheesecake", "Chiffon Cake", "Black Forest Cake")
        
        class CakeShop:
            cakes_to_make = cakes 
        """
        )

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.cakes: Tuple',
                                        'sandbox.module.cakes.0: Variable',
                                        'sandbox.module.cakes.1: Variable',
                                        'sandbox.module.cakes.2: Variable',
                                        'sandbox.module.CakeShop: Class',
                                        'sandbox.module.CakeShop.cakes_to_make: Reference')

        reloader.assert_actions('Update Module: sandbox.module',
                                 'DeepUpdate Tuple: sandbox.module.cakes',
                                 'Update Reference: sandbox.module.CakeShop.cakes_to_make')

        assert module.device.cakes == ("Cheesecake", "Chiffon Cake", "Black Forest Cake")
        assert module.device.CakeShop.cakes_to_make == ("Cheesecake", "Chiffon Cake", "Black Forest Cake")
        assert id(module.device.CakeShop.cakes_to_make) != cakes_id
        assert id(module.device.cakes) != cakes_id
        assert id(module.device.CakeShop.cakes_to_make) == id(module.device.cakes)

        reloader.rollback()
        assert_not_reloaded()
