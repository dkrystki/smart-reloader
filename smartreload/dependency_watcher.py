from pathlib import Path
from types import ModuleType
from typing import DefaultDict, Set

try:
    import builtins
except ImportError:
    import __builtin__ as builtins

import sys
from collections import defaultdict

__all__ = ("enable", "disable", "path_to_modules")

_baseimport = builtins.__import__
_blacklist = None
path_to_modules: DefaultDict[str, Set[ModuleType]] = defaultdict(set)

# PEP 328 changed the default level to 0 in Python 3.3.
_default_level = -1 if sys.version_info < (3, 3) else 0


def enable(blacklist=None) -> None:
    """Enable global module dependency tracking.

    A blacklist can be specified to exclude specific modules (and their import
    hierachies) from the reloading process.  The blacklist can be any iterable
    listing the fully-qualified names of modules that should be ignored.  Note
    that blacklisted modules will still appear in the dependency graph; they
    will just not be reloaded.
    """
    global _blacklist
    builtins.__import__ = _import
    if blacklist is not None:
        _blacklist = frozenset(blacklist)


def disable():
    """Disable global module dependency tracking."""
    global _blacklist, _parent
    builtins.__import__ = _baseimport


def _reset():
    global path_to_modules
    path_to_modules = defaultdict(set)


def register_module(module: ModuleType) -> None:
    path_to_modules[module.__file__].add(module)
    child_modules = [o for o in module.__dict__.values() if hasattr(o, "__file__")]
    for m in child_modules:
        path_to_modules[m.__file__].add(m)


def _import(name, globals=None, locals=None, fromlist=None, level=_default_level):
    """__import__() replacement function that tracks module dependencies."""
    # Track our current parent module.  This is used to find our current place
    # in the dependency graph.

    # Perform the actual import work using the base import function.
    base = _baseimport(name, globals, locals, fromlist, level)

    if hasattr(base, "__file__") and "site-packages" not in base.__file__:
        register_module(base)

    return base
