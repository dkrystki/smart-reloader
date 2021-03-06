from tests import utils
from tests.utils import Module, MockedPartialReloader


class TestDictionaries(utils.TestBase):
    def test_change_value(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """,
        )

        module.load()

        def assert_not_reloaded():
            module.assert_not_changed()
            reloader.assert_objects(module, 'sandbox.module.car_data: Dictionary',
                                            'sandbox.module.car_data.engine_power: DictionaryItem',
                                            'sandbox.module.car_data.max_speed: DictionaryItem',
                                            'sandbox.module.car_data.seats: DictionaryItem')
        assert_not_reloaded()

        module.replace('"engine_power": 200', '"engine_power": 250')

        reloader.reload(module)

        reloader.assert_objects(module, 'sandbox.module.car_data: Dictionary',
                                'sandbox.module.car_data.engine_power: DictionaryItem',
                                'sandbox.module.car_data.max_speed: DictionaryItem',
                                'sandbox.module.car_data.seats: DictionaryItem')

        reloader.assert_actions(
            "Update Module: sandbox.module",
            "Update DictionaryItem: sandbox.module.car_data.engine_power",
        )

        reloader.rollback()

    def test_change_key(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        car_data = {
        "max_speed": 150,
        "seats": 4,
        "engine_power": 200,
        }
        """,
        )

        module.load()

        def assert_not_reloaded():
            module.assert_not_changed()
            reloader.assert_objects(module, 'sandbox.module.car_data: Dictionary',
                                            'sandbox.module.car_data.max_speed: DictionaryItem',
                                            'sandbox.module.car_data.seats: DictionaryItem',
                                            'sandbox.module.car_data.engine_power: DictionaryItem')

        module.replace("engine_power", "engine_force")

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.car_data: Dictionary',
                                        'sandbox.module.car_data.max_speed: DictionaryItem',
                                        'sandbox.module.car_data.seats: DictionaryItem',
                                        'sandbox.module.car_data.engine_force: DictionaryItem')

        reloader.assert_actions(
            "Update Module: sandbox.module",
            "Add DictionaryItem: sandbox.module.car_data.engine_force",
            "Delete DictionaryItem: sandbox.module.car_data.engine_power",
        )

        assert "engine_power" not in module.device.car_data
        assert module.device.car_data["engine_force"] == 200

        reloader.rollback()
        assert_not_reloaded()

    def test_change_key_and_value(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        car_data = {
        "max_speed": 150,
        "seats": 4,
        "engine_power": 200,
        }
        """,
        )

        module.load()

        def assert_not_reloaded():
            module.assert_not_changed()
            reloader.assert_objects(module, 'sandbox.module.car_data: Dictionary',
                                    'sandbox.module.car_data.max_speed: DictionaryItem',
                                    'sandbox.module.car_data.seats: DictionaryItem',
                                    'sandbox.module.car_data.engine_power: DictionaryItem')
        assert_not_reloaded()

        module.replace('"engine_power": 200', '"engine_force": 250')

        reloader.reload(module)

        reloader.assert_objects(module, 'sandbox.module.car_data: Dictionary',
                                        'sandbox.module.car_data.max_speed: DictionaryItem',
                                        'sandbox.module.car_data.seats: DictionaryItem',
                                        'sandbox.module.car_data.engine_force: DictionaryItem')

        reloader.assert_actions(
            "Update Module: sandbox.module",
            "Add DictionaryItem: sandbox.module.car_data.engine_force",
            "Delete DictionaryItem: sandbox.module.car_data.engine_power",
        )

        assert "engine_power" not in module.device.car_data
        assert module.device.car_data["engine_force"] == 250

        reloader.rollback()
        assert_not_reloaded()

    def test_add(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        some_var = 1
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.some_var: Variable')
            module.assert_not_changed()
        assert_not_reloaded()

        module.rewrite(
            """
            some_var = 1

            car_data = {
            "engine_power": 200,
            "max_speed": 150,
            "seats": 4
            }
            """
        )

        reloader.reload(module)
        reloader.assert_actions(
            "Update Module: sandbox.module", "Add Dictionary: sandbox.module.car_data"
        )

        reloader.assert_objects(module, 'sandbox.module.some_var: Variable',
                                        'sandbox.module.car_data: Dictionary',
                                        'sandbox.module.car_data.engine_power: DictionaryItem',
                                        'sandbox.module.car_data.max_speed: DictionaryItem',
                                        'sandbox.module.car_data.seats: DictionaryItem')

        module.assert_obj_in("car_data")

        reloader.rollback()
        assert_not_reloaded()

    def test_delete(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        some_var = 1

        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """,
        )

        module.load()

        def assert_not_reloaded():
            module.assert_not_changed()
            reloader.assert_objects(module, 'sandbox.module.some_var: Variable',
                                            'sandbox.module.car_data: Dictionary',
                                            'sandbox.module.car_data.engine_power: DictionaryItem',
                                            'sandbox.module.car_data.max_speed: DictionaryItem',
                                            'sandbox.module.car_data.seats: DictionaryItem')
        assert_not_reloaded()

        module.rewrite(
            """
        some_var = 1
        """
        )

        reloader.reload(module)

        reloader.assert_objects(module, 'sandbox.module.some_var: Variable')
        reloader.assert_actions(
            "Update Module: sandbox.module", "Delete Dictionary: sandbox.module.car_data"
        )

        module.assert_obj_not_in("car_data")
        reloader.rollback()
        assert_not_reloaded()

    def test_rename(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        some_var = 1

        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """,
        )

        module.load()

        def assert_not_reloaded():
            module.assert_not_changed()
            reloader.assert_objects(module, 'sandbox.module.some_var: Variable',
                                    'sandbox.module.car_data: Dictionary',
                                    'sandbox.module.car_data.engine_power: DictionaryItem',
                                    'sandbox.module.car_data.max_speed: DictionaryItem',
                                    'sandbox.module.car_data.seats: DictionaryItem')

        assert_not_reloaded()

        module.replace("car_data", "car_specs")

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.some_var: Variable',
                                        'sandbox.module.car_specs: Dictionary',
                                        'sandbox.module.car_specs.engine_power: DictionaryItem',
                                        'sandbox.module.car_specs.max_speed: DictionaryItem',
                                        'sandbox.module.car_specs.seats: DictionaryItem')
        reloader.assert_actions(
            "Update Module: sandbox.module",
            "Add Dictionary: sandbox.module.car_specs",
            "Delete Dictionary: sandbox.module.car_data",
        )

        module.assert_obj_in("car_specs")
        module.assert_obj_not_in("car_data")

        reloader.rollback()
        assert_not_reloaded()

    def test_nested(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        cake_shop = {
        "cakes": 200,
        "cupcakes": 150,
        "clients": {
            "number": 100,
            "growth_per_month": 10
            }
        }
        """,
        )

        module.load()

        def assert_not_reloaded():
            reloader.assert_objects(module, 'sandbox.module.cake_shop: Dictionary',
                                    'sandbox.module.cake_shop.cakes: DictionaryItem',
                                    'sandbox.module.cake_shop.cupcakes: DictionaryItem',
                                    'sandbox.module.cake_shop.clients: Dictionary',
                                    'sandbox.module.cake_shop.clients.number: DictionaryItem',
                                    'sandbox.module.cake_shop.clients.growth_per_month: DictionaryItem')
            assert module.device.cake_shop["clients"]["number"] == 100

        assert_not_reloaded()

        module.replace('"number": 100', '"number": 150')

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.cake_shop: Dictionary',
                                'sandbox.module.cake_shop.cakes: DictionaryItem',
                                'sandbox.module.cake_shop.cupcakes: DictionaryItem',
                                'sandbox.module.cake_shop.clients: Dictionary',
                                'sandbox.module.cake_shop.clients.number: DictionaryItem',
                                'sandbox.module.cake_shop.clients.growth_per_month: DictionaryItem')

        reloader.assert_actions('Update Module: sandbox.module',
                                'Update DictionaryItem: sandbox.module.cake_shop.clients.number')

        assert module.device.cake_shop["clients"]["number"] == 150

        reloader.rollback()
        assert_not_reloaded()
        module.assert_not_changed()

    def test_nested_add(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        cake_shop = {
            "cakes": 200,
            "cupcakes": 150,
            "clients": None
        }
        """,
        )

        module.load()

        def assert_not_reloaded():
            assert module.device.cake_shop["clients"] is None
            module.assert_not_changed()
            reloader.assert_objects(module, 'sandbox.module.cake_shop: Dictionary',
                                             'sandbox.module.cake_shop.cakes: DictionaryItem',
                                             'sandbox.module.cake_shop.cupcakes: DictionaryItem',
                                             'sandbox.module.cake_shop.clients: DictionaryItem')

        assert_not_reloaded()

        module.rewrite("""
        cake_shop = {
            "cakes": 200,
            "cupcakes": 150,
            "clients": {
                "number": 12,
                "complains": 33 
            }
        }
        """)

        reloader.reload(module)
        reloader.assert_objects(module, 'sandbox.module.cake_shop: Dictionary',
                                        'sandbox.module.cake_shop.cakes: DictionaryItem',
                                        'sandbox.module.cake_shop.cupcakes: DictionaryItem',
                                        'sandbox.module.cake_shop.clients: Dictionary',
                                        'sandbox.module.cake_shop.clients.number: DictionaryItem',
                                        'sandbox.module.cake_shop.clients.complains: DictionaryItem')
        reloader.assert_actions('Update Module: sandbox.module', 'Update DictionaryItem: sandbox.module.cake_shop.clients')

        assert module.device.cake_shop["clients"]["number"] == 12

        reloader.rollback()
        assert_not_reloaded()

    def test_dynamically_created(self, sandbox):
        reloader = MockedPartialReloader(sandbox)

        module = Module(
            "module.py",
            """
        def create_dict():
            return {
                "cakes": 200,
                "cupcakes": 150,
                "clients": None,
                "meta": {
                    "shop_size_x": 100,
                    "shop_size_y": 100,
                }
            }
            
        cake_shop = create_dict() 
        """,
        )

        module.load()

        assert module.device.cake_shop["clients"] is None
        reloader.assert_objects(module, 'sandbox.module.create_dict: Function',
                                        'sandbox.module.cake_shop: Dictionary',
                                        'sandbox.module.cake_shop.cakes: DictionaryItem',
                                        'sandbox.module.cake_shop.cupcakes: DictionaryItem',
                                        'sandbox.module.cake_shop.clients: DictionaryItem',
                                        'sandbox.module.cake_shop.meta: Dictionary',
                                        'sandbox.module.cake_shop.meta.shop_size_x: DictionaryItem',
                                        'sandbox.module.cake_shop.meta.shop_size_y: DictionaryItem')

        module.rewrite("""
        def create_dict():
            return {
                "cakes": 200,
                "cupcakes": 150,
                "clients": 300,
                "meta": {
                    "shop_size_x": 200,
                    "shop_size_y": 100,
                },
                "extra_meta": {
                    "employees": 5
                }
            }
            
        cake_shop = create_dict()
        """)

        reloader.reload(module)

        reloader.assert_objects(module,
                                'sandbox.module.create_dict: Function',
                                'sandbox.module.cake_shop: Dictionary',
                                'sandbox.module.cake_shop.cakes: DictionaryItem',
                                'sandbox.module.cake_shop.cupcakes: DictionaryItem',
                                'sandbox.module.cake_shop.clients: DictionaryItem',
                                'sandbox.module.cake_shop.meta: Dictionary',
                                'sandbox.module.cake_shop.meta.shop_size_x: DictionaryItem',
                                'sandbox.module.cake_shop.meta.shop_size_y: DictionaryItem',
                                'sandbox.module.cake_shop.extra_meta: Dictionary',
                                'sandbox.module.cake_shop.extra_meta.employees: DictionaryItem')

        reloader.assert_actions('Update Module: sandbox.module',
                                 'Update Function: sandbox.module.create_dict',
                                 'Add Dictionary: sandbox.module.cake_shop.extra_meta',
                                 'Update DictionaryItem: sandbox.module.cake_shop.clients',
                                 'Update DictionaryItem: sandbox.module.cake_shop.meta.shop_size_x')

        assert module.device.cake_shop == {
            "cakes": 200,
            "cupcakes": 150,
            "clients": 300,
            "meta": {
                "shop_size_x": 200,
                "shop_size_y": 100,
            },
            "extra_meta": {
                "employees": 5
            }
        }

        reloader.rollback()
        module.assert_not_changed()
