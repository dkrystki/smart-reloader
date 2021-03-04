from threading import Thread
from time import sleep

from tests import utils
from tests.utils import Module, MockedPartialReloader


# class TestReloadFrames(utils.TestBase):
#     def test_basic(self, sandbox):
#         reloader = MockedReloader(sandbox)
#
#         module = Module(
#             "module.py",
#             """
#         from time import sleep
#         glob_var = 'test_1'
#
#         def start():
#             elements = []
#
#             elements.append(glob_var)
#             sleep(1)
#
#             elements.append(glob_var)
#             sleep(1)
#
#             elements.append(glob_var)
#             sleep(1)
#
#             elements.append(glob_var)
#             sleep(1)
#
#             return elements
#         """,
#         )
#         module.load()
#
#         def reload(old_str: str, new_str: str):
#             def fun():
#                 sleep(1)
#                 module.replace(old_str, new_str)
#                 reloader.reload(module)
#
#             Thread(target=fun).start()
#
#         ret = module.device.start()
#         reload("test_1", "test_2")
#         reload("test_2", "test_3")
#         reload("test_3", "test_4")
#
#         assert ret == ["test_1", "test_2", "test_3", "test_4"]
#
