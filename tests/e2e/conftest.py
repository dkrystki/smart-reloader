from pytest import fixture

from tests.e2e.utils import SmartReloader

from . import utils


@fixture
def smartreloader() -> SmartReloader:

    s = SmartReloader()
    yield s
    s.on_exit()
