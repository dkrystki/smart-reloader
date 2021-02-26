import pytest

from tests import utils
from tests.utils import Module, Reloader


class TestLists(utils.TestBase):
    def test_basic(self, sandbox, capsys):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        cakes = ["Cheesecake", "Chiffon Cake"]
        """,
        )

        module.load()

        cakes_id = id(module.device.cakes)

        module.rewrite(
            """
        cakes = ["Cheesecake", "Chiffon Cake", "Black Forest Cake"]
        """
        )

        reloader.reload(module)

        reloader.assert_actions('Update Module: module', 'Update List: module.cakes')

        assert module.device.cakes == ["Cheesecake", "Chiffon Cake", "Black Forest Cake"]
        assert cakes_id == id(module.device.cakes)

    def test_nested(self, sandbox, capsys):
        reloader = Reloader(sandbox)

        module = Module(
            "module.py",
            """
        sweets = ["cheesecake", "Chiffon Cake", ["Cupcake", "Cookie"]]
        """,
        )

        module.load()

        sweets_id = id(module.device.sweets)
        nested_id = id(module.device.sweets[-1])

        module.rewrite(
            """
        sweets = ["cheesecake", "Chiffon Cake", ["Cupcake", "Cookie", "Macaroon"]]
        """
        )

        reloader.reload(module)

        reloader.assert_actions('Update Module: module', 'Update List: module.sweets')

        assert module.device.sweets == ["cheesecake", "Chiffon Cake", ["Cupcake", "Cookie", "Macaroon"]]
        # assert sweets_id == id(module.device.sweets)
        # assert nested_id == id(module.device.sweets[-1])

    def test_fixes_references(self, sandbox, capsys):
        reloader = Reloader(sandbox)

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
        reloader.assert_actions('Update Module: module', 'Update List: module.sweets')

        assert module.device.sweets == [module.device.Cheesecake, module.device.ChiffonCake,
                                        [module.device.Cupcake, module.device.Cookie, module.device.Macaroon]]

        assert sweets_id == id(module.device.sweets)

    def test_tuples(self, sandbox, capsys):
        reloader = Reloader(sandbox)

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

        module.rewrite(
            """
        cakes = ("Cheesecake", "Chiffon Cake", "Black Forest Cake")
        
        class CakeShop:
            cakes_to_make = cakes 
        """
        )

        reloader.reload(module)

        reloader.assert_actions('Update Module: module',
                                 'DeepUpdate Tuple: module.cakes',
                                 'Update Reference: module.CakeShop.cakes_to_make')

        assert module.device.cakes == ("Cheesecake", "Chiffon Cake", "Black Forest Cake")
        assert module.device.CakeShop.cakes_to_make == ("Cheesecake", "Chiffon Cake", "Black Forest Cake")
        assert id(module.device.CakeShop.cakes_to_make) != cakes_id
        assert id(module.device.cakes) != cakes_id
        assert id(module.device.CakeShop.cakes_to_make) == id(module.device.cakes)