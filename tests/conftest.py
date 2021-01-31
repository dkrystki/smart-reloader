import os
import shutil
import sys
from pathlib import Path

from pytest import fixture, register_assert_rewrite

register_assert_rewrite("tests.utils")


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
