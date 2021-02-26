from smartreload.modules import Source
from tests import utils
from tests.utils import Module, Reloader


class TestFlatNames(utils.TestBase):
    def test_dictionary(self, sandbox):
        module = Module(
            "module.py",
            """
        import time
            
        cake_shop = {
            "cakes": 200,
            "cupcakes": 150,
            "clients": {
                "number": 12,
                "complains": 33 
            },
            10: "test_number_as_key",
            time: "test_weird_keys"
        }
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax == ['cake_shop',
                                      'cake_shop.cakes',
                                      'cake_shop.cupcakes',
                                      'cake_shop.clients',
                                      'cake_shop.clients.number',
                                      'cake_shop.clients.complains',
                                      'cake_shop.10',
                                      'cake_shop.time']

    def test_classes(self, sandbox):
        module = Module(
            "module.py",
            """
        import time
        
        global_name = "test_name"
        first_name, second_name = ("test_name1", "test_name2")

        class CakeShop:
            class Meta:
                employee_number = 5
                
                @classmethod
                def get_employee_number(cls):
                    return cls.employee_number
        
            cake_n: int
            shop_name: str = "Peanut butter heaven"
            tuple1, tuple2 = ("test_name1", "test_name2")
            
            data = {
                "cakes": 200,
                "cupcakes": 150,
                "clients": {
                    "number": 12,
                    "complains": 33 
                },
                10: "test_number_as_key",
                time: "test_weird_keys"
            }
         
            def __init__(self) -> None:
                self.cake_n = 10
                
            def open(self) -> str:
                return "opened"
                
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax == ['global_name',
 'first_name',
 'first_name.0',
 'first_name.1',
 'second_name',
 'second_name.0',
 'second_name.1',
 'CakeShop',
 'CakeShop.Meta',
 'CakeShop.Meta.employee_number',
 'CakeShop.Meta.get_employee_number',
 'CakeShop.cake_n',
 'CakeShop.shop_name',
 'CakeShop.tuple1',
 'CakeShop.tuple1.0',
 'CakeShop.tuple1.1',
 'CakeShop.tuple2',
 'CakeShop.tuple2.0',
 'CakeShop.tuple2.1',
 'CakeShop.data',
 'CakeShop.data.cakes',
 'CakeShop.data.cupcakes',
 'CakeShop.data.clients',
 'CakeShop.data.clients.number',
 'CakeShop.data.clients.complains',
 'CakeShop.data.10',
 'CakeShop.data.time',
 'CakeShop.__init__',
 'CakeShop.open']

    def test_lambdas(self, sandbox):
        module = Module(
            "module.py",
            """
        from typing import Callable
        
        global_name = lambda x: "Alison"

        class CakeShop:
            cake_n: Callable = lambda: 10
            data = {
                "cakes": lambda: 14,
                "clients": {
                    "number": lambda: 88
                },
            }

        """,
        )

        source = Source(module.path)
        assert source.flat_syntax == ['global_name',
                                     'CakeShop',
                                     'CakeShop.cake_n',
                                     'CakeShop.data',
                                     'CakeShop.data.cakes',
                                     'CakeShop.data.clients',
                                     'CakeShop.data.clients.number']

    def test_lists(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ["Cheesecake", "Crepe Cake"]
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax == ['cakes',
                                      'cakes.0',
                                      "cakes.1"]

    def test_tuples(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ("Cheesecake", "Crepe Cake")
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax == ['cakes',
                                      'cakes.0',
                                      "cakes.1"]

    def test_lists_nested(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ["Cheesecake", "Crepe Cake", ["Cupcake", "Eclair", ["Macaroon"]]]
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax == ['cakes',
                                     'cakes.0',
                                     'cakes.1',
                                     'cakes.2',
                                     'cakes.2.0',
                                     'cakes.2.1',
                                     'cakes.2.2',
                                     'cakes.2.2.0']

    def test_tuples_nested(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ("Cheesecake", "Crepe Cake", ("Cupcake", "Eclair", ("Macaroon",)))
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax == ['cakes',
                                     'cakes.0',
                                     'cakes.1',
                                     'cakes.2',
                                     'cakes.2.0',
                                     'cakes.2.1',
                                     'cakes.2.2',
                                     'cakes.2.2.0']