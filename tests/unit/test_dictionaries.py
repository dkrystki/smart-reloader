from tests import utils
from tests.utils import Module, Reloader


class TestDictionaries(utils.TestBase):
    def test_change_value(self, sandbox):
        module = Module("module.py",
            """
        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """
        )

        module.load()
        assert module.device.car_data["engine_power"] == 200

        module.replace('"engine_power": 200','"engine_power": 250')

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
            "Update: Module: module",
            "Update: DictionaryItem: module.car_data.engine_power"
        )

        assert module.device.car_data["engine_power"] == 250

    def test_change_key(self, sandbox):
        module = Module("module.py",
            """
        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """
        )

        module.load()
        assert module.device.car_data["engine_power"] == 200

        module.replace("engine_power", "engine_force")

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
        "Update: Module: module",
        "Add: DictionaryItem: module.car_data.engine_force",
        "Delete: DictionaryItem: module.car_data.engine_power",
        )

        assert "engine_power" not in module.device.car_data
        assert module.device.car_data["engine_force"] == 200

    def test_change_key_and_value(self, sandbox):
        module = Module("module.py",
            """
        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """
        )

        module.load()
        assert module.device.car_data["engine_power"] == 200

        module.replace('"engine_power": 200', '"engine_force": 250')

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
        "Update: Module: module",
        "Add: DictionaryItem: module.car_data.engine_force",
        "Delete: DictionaryItem: module.car_data.engine_power",
        )

        assert "engine_power" not in module.device.car_data
        assert module.device.car_data["engine_force"] == 250

    def test_add(self, sandbox):
        module = Module("module.py",
        """
        some_var = 1
        """
        )

        module.load()
        module.assert_obj_not_in("car_data")

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

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions("Update: Module: module", "Add: Dictionary: module.car_data")

        module.assert_obj_in("car_data")

    def test_delete(self, sandbox):
        module = Module("module.py",
        """
        some_var = 1

        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """
        )

        module.load()
        module.assert_obj_in("car_data")

        module.rewrite(
        """
        some_var = 1
        """
        )

        reloader = Reloader(sandbox)
        reloader.reload(module)
        reloader.assert_actions("Update: Module: module", "Delete: Dictionary: module.car_data")

        module.assert_obj_not_in("car_data")

    def test_rename(self, sandbox):
        module = Module("module.py",
        """
        some_var = 1

        car_data = {
        "engine_power": 200,
        "max_speed": 150,
        "seats": 4
        }
        """
        )

        module.load()

        module.assert_obj_in("car_data")

        module.replace("car_data", "car_specs")

        reloader = Reloader(sandbox)
        reloader.reload(module)

        reloader.assert_actions(
        "Update: Module: module",
        "Add: Dictionary: module.car_specs",
        "Delete: Dictionary: module.car_data"
        )

        module.assert_obj_in("car_specs")
        module.assert_obj_not_in("car_data")
