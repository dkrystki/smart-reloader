# flake8: noqa E402, F401
from rich.console import Console
from rich.traceback import install

install()

console = Console()
console._force_terminal = True
console.soft_wrap = True

from .config import BaseConfig
from .exceptions import *
from .partialreloader import *
