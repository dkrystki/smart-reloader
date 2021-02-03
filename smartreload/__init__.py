# flake8: noqa E402, F401

# import warnings
# sys.stderr = lambda x: None

# warnings.warn = lambda *args, **kwargs: None
# warnings._showwarnmsg = lambda x: None

# warnings.simplefilter("ignore")

from rich.console import Console
from rich.traceback import install

install()

console = Console()
console._force_terminal = True
console.soft_wrap = True

# from . import dependency_watcher
from .partialreloader import *

# dependency_watcher.enable()
