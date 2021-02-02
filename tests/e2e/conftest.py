from pytest import fixture

from . import utils
from tests.e2e.utils import SmartReload


@fixture
def smartreload() -> SmartReload:

    s = SmartReload()
    yield s
    s.on_exit()
