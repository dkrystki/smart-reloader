import sys
from collections import defaultdict
from typing import Set, Dict, DefaultDict

try:
    import builtins
except ImportError:
    import __builtin__ as builtins


STAR_IMPORTS = "__smart_reload_star_imports__"

_baseimport = builtins.__import__


def enable():
    builtins.__import__ = _import

def disable():
    global _baseimport
    builtins.__import__ = _baseimport


_default_level = -1 if sys.version_info < (3, 3) else 0

module_file_to_start_import_usages: DefaultDict[str, Set[str]] = defaultdict(set)


def _import(name, globals=None, locals=None, fromlist=None, level=_default_level):
    if globals:
        for f, usages in module_file_to_start_import_usages.copy().items():
            if globals["__file__"] not in module_file_to_start_import_usages[f]:
                continue
            module_file_to_start_import_usages[f].remove(globals["__file__"])

    base = _baseimport(name, globals, locals, fromlist, level)
    setattr(base, STAR_IMPORTS, set())

    if globals and hasattr(base, "__file__") and "site-packages" not in base.__file__ and "python3.6" not in base.__file__:
        if base is not None:
            m = base

            # We manually walk through the imported hierarchy because the import
            # function only returns the top-level package reference for a nested
            # import statement (e.g. 'package' for `import package.module`) when
            # no fromlist has been specified.  It's possible that the package
            # might not have all of its descendents as attributes, in which case
            # we fall back to using the immediate ancestor of the module instead.

            # If this is a nested import for a reloadable (source-based) module,
            # we append ourself to our parent's dependency list.

            if fromlist and "*" in fromlist:
                module_file_to_start_import_usages[base.__file__].add(globals["__file__"])

            # trace_var_name = f"smart_reload_start_import_trace__{name}__"
            # setattr(m, trace_var_name, f"smart_reload_meta_{name}")
            # m.__all__.append(trace_var_name)

    return base

