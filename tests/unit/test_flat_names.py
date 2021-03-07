from collections import OrderedDict

from smartreloader.objects.modules import Source
from tests import utils
from tests.utils import Module


class TestFlatNames(utils.TestBase):
    def test_global_variables(self, sandbox):
        module = Module(
            "module.py",
            """
        global_name = "test_name"
        first_name, second_name = ("test_name1", "test_name2")
        cake_n: int
        shop_name: str = "Peanut butter heaven"
        calculation = 1 / 0 
        calculation_2 = False or True
        attribute_name = Attribute.name
        random_name, random_number = get_name_and_number() 
        tuple1, tuple2 = ("test_name1", "test_name2")
        dict_1, dict_2 = ({"a": 1, "b": 2}, {"c": 3, "d": 4})
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict(
            {'global_name': 'Str',
             'first_name': 'Str',
             'second_name': 'Str',
             'shop_name': 'Str',
             'calculation': 'Op',
             'calculation_2': 'Op',
             'attribute_name': 'Attribute',
             'random_name': 'Call',
             'random_number': 'Call',
             'tuple1': 'Str',
             'tuple2': 'Str',
             'dict_1': 'DictType',
             'dict_1.a': 'Num',
             'dict_1.b': 'Num',
             'dict_2': 'DictType',
             'dict_2.c': 'Num',
             'dict_2.d': 'Num'
             })

    def test_functions(self, sandbox):
        module = Module(
            "module.py",
            """
        def fun1():
            return 1
            
        def fun2(arg: str):
            return 2
            
        def fun3(arg: str) -> int:
            return 2
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict({'fun1': 'FunctionDef',
                                                      'fun2': 'FunctionDef',
                                                      'fun3': 'FunctionDef'})

    def test_dictionary(self, sandbox):
        module = Module(
            "module.py",
            """
        cake_shop = {
            "cakes": 200,
            "cupcakes": 150,
            "clients": {
                "number": 12,
                "complains": 33,
                "test_none": None
            },
            10: "test_number_as_key",
            time: "test_weird_keys"
        }
        """,
        )
        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict({
            'cake_shop': 'DictType',
            'cake_shop.cakes': 'Num',
            'cake_shop.cupcakes': 'Num',
            'cake_shop.clients': 'DictType',
            'cake_shop.clients.number': 'Num',
            'cake_shop.clients.complains': 'Num',
            'cake_shop.clients.test_none': 'NameConstant',
            'cake_shop.10': 'Str',
            'cake_shop.time': 'Str'
        })

    def test_classes(self, sandbox):
        module = Module(
            "module.py",
            """
        class CakeShop:
            class Meta:
                employee_number = 5
                
                @classmethod
                def get_employee_number(cls):
                    return cls.employee_number
        
            cake_n: int
            shop_name: str = "Peanut butter heaven"
            random_name, random_number = get_name_and_number() 
            tuple1, tuple2 = ("test_name1", "test_name2")
            dict_1, dict_2 = ({"a": 1, "b": 2}, {"c": 3, "d": 4})
            
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

        assert source.flat_syntax_str == OrderedDict(
            {'CakeShop': 'Class',
             'CakeShop.Meta': 'Class',
             'CakeShop.Meta.employee_number': 'Num',
             'CakeShop.Meta.get_employee_number': 'FunctionDef',
             'CakeShop.shop_name': 'Str',
             'CakeShop.random_name': 'Call',
             'CakeShop.random_number': 'Call',
             'CakeShop.tuple1': 'Str',
             'CakeShop.tuple2': 'Str',
             'CakeShop.dict_1': 'DictType',
             'CakeShop.dict_1.a': 'Num',
             'CakeShop.dict_1.b': 'Num',
             'CakeShop.dict_2': 'DictType',
             'CakeShop.dict_2.c': 'Num',
             'CakeShop.dict_2.d': 'Num',
             'CakeShop.data': 'DictType',
             'CakeShop.data.cakes': 'Num',
             'CakeShop.data.cupcakes': 'Num',
             'CakeShop.data.clients': 'DictType',
             'CakeShop.data.clients.number': 'Num',
             'CakeShop.data.clients.complains': 'Num',
             'CakeShop.data.10': 'Str',
             'CakeShop.data.time': 'Str',
             'CakeShop.__init__': 'FunctionDef',
             'CakeShop.open': 'FunctionDef'
             })

    def test_lambdas(self, sandbox):
        module = Module(
            "module.py",
            """
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
        assert source.flat_syntax_str == OrderedDict({
            'global_name': 'Lambda',
            'CakeShop': 'Class',
            'CakeShop.cake_n': 'Lambda',
            'CakeShop.data': 'DictType',
            'CakeShop.data.cakes': 'Lambda',
            'CakeShop.data.clients': 'DictType',
            'CakeShop.data.clients.number': 'Lambda',
        })

    def test_lists(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ["Cheesecake", "Crepe Cake"]
        """,
        )
        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict(
            {
                'cakes': 'List',
                'cakes.0': 'Str',
                'cakes.1': 'Str'
            }
        )

    def test_imports(self, sandbox):
        module = Module(
            "module.py",
            """
        import math
        import pathlib, os, sys
        import numpy as np
        
        from numpy import pi, multiply  
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict({'math': 'Imported',
                                                      'pathlib': 'Imported',
                                                       'os': 'Imported',
                                                       'sys': 'Imported',
                                                       'np': 'Imported',
                                                       'pi': 'Imported',
                                                       'multiply': 'Imported'})

    def test_tuples(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ("Cheesecake", "Crepe Cake")
        """,
        )


        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict({'cakes': 'Tuple',
                                                      'cakes.0': 'Str',
                                                      'cakes.1': 'Str'})

    def test_lists_nested(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ["Cheesecake", "Crepe Cake", ["Cupcake", "Eclair", ["Macaroon"]]]
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict({'cakes': 'List',
                                                      'cakes.0': 'Str',
                                                      'cakes.1': 'Str',
                                                      'cakes.2': 'List',
                                                      'cakes.2.0': 'Str',
                                                      'cakes.2.1': 'Str',
                                                      'cakes.2.2': 'List',
                                                      'cakes.2.2.0': 'Str'})

    def test_tuples_nested(self, sandbox):
        module = Module(
            "module.py",
            """
        cakes = ("Cheesecake", "Crepe Cake", ("Cupcake", "Eclair", ("Macaroon",)))
        """,
        )

        source = Source(module.path)
        assert source.flat_syntax_str == OrderedDict({'cakes': 'Tuple',
             'cakes.0': 'Str',
             'cakes.1': 'Str',
             'cakes.2': 'Tuple',
             'cakes.2.0': 'Str',
             'cakes.2.1': 'Str',
             'cakes.2.2': 'Tuple',
             'cakes.2.2.0': 'Str'})
