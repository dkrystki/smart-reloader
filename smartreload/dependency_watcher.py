import sys
import types
from collections import defaultdict
from types import ModuleType
from typing import DefaultDict, Dict, Set, List, Callable, Optional
import time


try:
    import builtins
except ImportError:
    import __builtin__ as builtins


_baseimport = builtins.__import__

import sys
from os.path import isdir
from importlib import invalidate_caches
from importlib.machinery import FileFinder
from importlib import invalidate_caches
from importlib.machinery import SourceFileLoader

post_module_exec_hook: Optional[Callable] = None

class MyLoader(SourceFileLoader):
    def exec_module(self, module: types.ModuleType) -> None:
        init_import(module)
        super().exec_module(module)
        post_import(module)
        if post_module_exec_hook:
            post_module_exec_hook(module)


once = False


def enable():
    global once

    if once:
        return

    builtins.__import__ = _import

    hook_index, hook = next((i, h) for i, h in enumerate(sys.path_hooks) if "FileFinder" in h.__name__)

    def new_hook(path: str):
        finder = hook(path)
        if "site-packages" in path or "python3" in path:
            return finder
        finder._loaders.insert(0, (".py", MyLoader))
        return finder

    sys.path_hooks[hook_index] = new_hook
    sys.path_importer_cache.clear()
    invalidate_caches()
    once = True

def disable():
    global _baseimport
    builtins.__import__ = _baseimport


_default_level = -1 if sys.version_info < (3, 3) else 0
module_file_to_start_import_usages: DefaultDict[str, Set[str]] = defaultdict(set)
import_order: List[str] = []
last_import_time = time.time()


def reset():
    global module_file_to_start_import_usages
    global import_order

    module_file_to_start_import_usages = defaultdict(set)
    import_order = []


def is_file_foreign(file: str):
    ret = (
        "site-packages" in file or "python3.6" in file or "pycharm-professional" in file
    )
    return ret


def init_import(module: ModuleType):
    if not module:
        return

    if not hasattr(module, "__file__"):
        return

    module_file = module.__file__

    if not module_file:
        return

    if is_file_foreign(module_file):
        return

    clear_start_import_usages(module_file)


def clear_start_import_usages(module_file: str):
    # clear all usages
    for f, usages in module_file_to_start_import_usages.copy().items():
        if module_file not in module_file_to_start_import_usages[f]:
            continue
        module_file_to_start_import_usages[f].remove(module_file)


def extract_star_import_info(module: ModuleType, globals, fromlist):
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


def seconds_from_last_import() -> float:
    global last_import_time
    ret = time.time() - last_import_time
    return ret


def post_import(module: ModuleType):
    try:
        module_file = getattr(module, "__file__", None)
    except:
        return

    if not module_file:
        return

    if is_file_foreign(module_file):
        return

    if hasattr(module, "__file__") and module.__file__ not in import_order:
        import_order.append(module.__file__)


def _import(name, globals=None, locals=None, fromlist=None, level=_default_level):
    global last_import_time
    last_import_time = time.time()

    base = _baseimport(name, globals, locals, fromlist, level)

    if base is not None and fromlist and "*" in fromlist:
        extract_star_import_info(base, globals, fromlist)

    # if fromlist:
    #     for m in fromlist:
    #         if m == "*":
    #             continue
    #         post_import(getattr(base, m))

    return base

