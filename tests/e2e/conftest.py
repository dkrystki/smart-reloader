from pytest import fixture

from tests.e2e.utils import SmartReload

from . import utils


@fixture
def smartreload() -> SmartReload:

    s = SmartReload()
    yield s
    s.on_exit()
