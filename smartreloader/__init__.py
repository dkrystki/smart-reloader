# flake8: noqa E402, F401
import os

from rich.console import Console
from rich.traceback import install

from . import e2e

install()

console = Console()
console._force_terminal = True
console.soft_wrap = True

from .config import BaseConfig
from .exceptions import *
from .partialreloader import *
