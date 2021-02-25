from smartreload.partialreloader import Source
from tests import utils
from tests.utils import Module, Reloader


class TestDictionaries(utils.TestBase):
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
        assert source.flat_syntax == ['employee_number',
                                     'cake_n',
                                     'shop_name',
                                     'data',
                                     'data.cakes',
                                     'data.cupcakes',
                                     'data.clients',
                                     'data.clients.number',
                                     'data.clients.complains',
                                     'data.10',
                                     'data.time']
