import sys
from collections import defaultdict
from typing import DefaultDict, Dict, Set

try:
    import builtins
except ImportError:
    import __builtin__ as builtins


_baseimport = builtins.__import__


def enable():
    builtins.__import__ = _import


def disable():
    global _baseimport
    builtins.__import__ = _baseimport


_default_level = -1 if sys.version_info < (3, 3) else 0

module_file_to_start_import_usages: DefaultDict[str, Set[str]] = defaultdict(set)


def is_file_foreign(file: str):
    ret = (
        "site-packages" in file or "python3.6" in file or "pycharm-professional" in file
    )
    return ret


def init_import(globals):
    if not globals:
        return

    module_file = globals.get("__file__", None)

    if not module_file:
        return

    if is_file_foreign(module_file):
        return

    for f, usages in module_file_to_start_import_usages.copy().items():
        if module_file not in module_file_to_start_import_usages[f]:
            continue
        module_file_to_start_import_usages[f].remove(module_file)


def extract_star_import_info(module, globals, fromlist):
    if not globals:
        return

    parent_module_file = globals.get("__file__", None)

    if not parent_module_file:
        return

    if is_file_foreign(parent_module_file):
        return

    imported_module_file = module.__dict__.get("__file__", None)

    if not imported_module_file or is_file_foreign(imported_module_file):
        return

    module_file_to_start_import_usages[imported_module_file].add(parent_module_file)


def _import(name, globals=None, locals=None, fromlist=None, level=_default_level):
    init_import(globals)
    base = _baseimport(name, globals, locals, fromlist, level)

    if base is not None and fromlist and "*" in fromlist:
        extract_star_import_info(base, globals, fromlist)

    return base
