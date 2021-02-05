import os
import shutil
import sys
from pathlib import Path

from pytest import fixture, register_assert_rewrite

register_assert_rewrite("tests.utils")


@fixture
def env_sandbox() -> Path:
    environ_before = os.environ.copy()

    yield
    os.environ = environ_before


@fixture
def modules_sandbox() -> Path:
    modules_before = sys.modules.copy()

    yield

    diff = sys.modules.keys() - modules_before.keys()

    for m in diff:
        del sys.modules[m]

    sys.modules = modules_before


@fixture
def sandbox() -> Path:
    pwd = Path(os.environ["PWD"])

    test_dir = Path(os.getenv("PYTEST_CURRENT_TEST").split("::")[0]).parent

    sandbox_dir = pwd / test_dir / "sandbox"
    if sandbox_dir.exists():
        shutil.rmtree(str(sandbox_dir), ignore_errors=True)

    sys.path.insert(0, str(sandbox_dir))

    if not sandbox_dir.exists():
        sandbox_dir.mkdir()
        (sandbox_dir / "__init__.py").touch()
    os.chdir(str(sandbox_dir))

    return sandbox_dir


@fixture
def is_windows():
    from smartreload.misc import is_windows

    return is_windows()


@fixture
def is_linux():
    from smartreload.misc import is_linux

    return is_linux()
