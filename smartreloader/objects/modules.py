import ast
import sys
from collections import OrderedDict, defaultdict
from logging import Logger

from dataclasses import field
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    DefaultDict,
    Dict,
    List,
    Optional,
    Type, TYPE_CHECKING, Tuple, )

from smartreloader import misc

from dataclasses import dataclass

from smartreloader.objects.base_objects import BaseAction, Object, ContainerObj

if TYPE_CHECKING:
    from smartreloader.partialreloader import PartialReloader


@dataclass
class Source:
    path: Path
    content: str = field(init=False)
    syntax: ast.AST = field(init=False)
    flat_syntax: List[str] = field(init=False)

    @dataclass
    class NamedNode:
        name: str
        content: Optional[ast.AST]
        parent: str

        def __repr__(self) -> str:
            return self.full_name

        @property
        def full_name(self) -> str:
            ret = f"{self.parent}.{self.name}" if self.parent else self.name
            return ret

        @classmethod
        def _get_ast_name(cls, node: ast.AST) -> Optional[str]:
            if isinstance(node, ast.Str):
                return node.s

            if isinstance(node, ast.Num):
                return node.n

            if isinstance(node, ast.Name):
                return node.id

            if isinstance(node, ast.ClassDef):
                return node.name

            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                return node.name

            return None

        def _get_child_nodes(self) -> List["Source.NamedNode"]:
            if isinstance(self.content, ast.Module) or isinstance(self.content, ast.ClassDef):
                return self._get_child_nodes_for_body()

            if isinstance(self.content, ast.Dict):
                return self._get_child_nodes_for_dict()

            if isinstance(self.content, ast.List) or isinstance(self.content, ast.Tuple):
                return self._get_child_nodes_for_iterable()

            return []

        def _get_child_nodes_for_body(self) -> List["Source.NamedNode"]:
            nodes = []

            for b in self.content.body:
                if type(b) in [ast.Assign, ast.AnnAssign]:
                    targets = b.targets if hasattr(b, "targets") else [b.target]
                    for t in targets:
                        if isinstance(t, ast.Tuple):
                            for n in t.elts:
                                nodes.append(Source.NamedNode(self._get_ast_name(n), b.value, self.full_name))
                        else:
                            nodes.append(Source.NamedNode(self._get_ast_name(t), b.value, self.full_name))

                if isinstance(b, ast.ClassDef):
                    nodes.append(Source.NamedNode(self._get_ast_name(b), b, self.full_name))
                elif isinstance(b, ast.FunctionDef) or isinstance(b, ast.AsyncFunctionDef):
                    nodes.append(Source.NamedNode(self._get_ast_name(b), None, self.full_name))

            return nodes

        def _get_child_nodes_for_dict(self) -> List["Source.NamedNode"]:
            ret = []
            for k, v in zip(self.content.keys, self.content.values):
                ret.append(Source.NamedNode(self._get_ast_name(k), v, self.full_name))

            return ret

        def _get_child_nodes_for_iterable(self) -> List["Source.NamedNode"]:
            ret = []
            for i, v in enumerate(self.content.elts):
                name = str(i)
                ret.append(Source.NamedNode(name, v, self.full_name))

            return ret

        def get_flat(self) -> List[str]:
            ret = []
            if self.full_name:
                ret.append(self.full_name)

            for n in self._get_child_nodes():
                ret.extend(n.get_flat())

            return ret

    def __post_init__(self) -> None:
        self.content = self.path.read_text()
        self.syntax = ast.parse(self.content, str(self.path))
        self.flat_syntax = []
        self.flat_syntax = self._get_flat_container_names(self.syntax)
        pass

    def fetch_source(self):
        self.source = Source(self.path)

    def _get_namespaced_name(self, parent: str, name: str) -> str:
        return f"{parent}.{name}" if parent else name

    def _get_flat_container_names(self, syntax: ast.AST) -> List[str]:
        if not hasattr(syntax, "body"):
            return []

        parent_node = self.NamedNode("", self.syntax, "")
        ret = parent_node.get_flat()
        return ret


@dataclass(repr=False)
class ModuleDescriptor:
    reloader: "PartialReloader"
    name: str
    path: Path
    body: ModuleType
    source: Source = field(init=False)
    module_obj: "Module" = field(init=False, default=None)

    def __post_init__(self):
        self.fetch_source()

    def post_execute(self):
        self.module_obj = Module(module_descriptor=self,
                                 name=None,
                                 python_obj=self.body,
                                 parent=None,
                                 reloader=self.reloader,
                                 module=None)

    def fetch_source(self) -> None:
        self.source = Source(self.path)

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self) -> str:
        return self.name


class Modules(dict):
    user_modules: DefaultDict[str, List[ModuleDescriptor]]

    def __init__(
        self, reloader: "PartialReloader", old_dict: Dict[str, ModuleType]
    ) -> None:
        super().__init__()
        self.reloader = reloader
        self._dict = old_dict
        self.user_modules = defaultdict(list)

    def __setitem__(self, key: str, value: ModuleType) -> None:
        self._dict.__setitem__(key, value)
        if not hasattr(value, "__file__"):
            return

        if self.reloader.root not in Path(value.__file__).parents:
            return

        file = Path(value.__file__)
        module = ModuleDescriptor(name = key,
                              path=file,
                              body=value,
                                reloader=self.reloader)
        self.user_modules[value.__file__].append(module)

    def __getitem__(self, key: str):
        return self._dict.__getitem__(key)

    def __contains__(self, item):
        return self._dict.__contains__(item)

    def get(self, *args, **kwargs):
        return self._dict.get(*args, **kwargs)

    def values(self):
        return self._dict.values()

    def keys(self):
        return self._dict.keys()

    def pop(self, *args, **kwargs):
        return self._dict.pop(*args, **kwargs)

    def __delattr__(self, item):
        return self._dict.__delattr__(item)

    def __delete__(self, instance):
        return self._dict.__delete__(instance)

    def __delitem__(self, *args, **kwargs):
        return self._dict.__delitem__(*args, **kwargs)


@dataclass(repr=False)
class UpdateModule(BaseAction):
    module_file: Path
    priority = 50
    module_descriptor: "ModuleDescriptor" = field(init=False)

    logger: Logger = field(init=False)

    def __post_init__(self) -> None:
        self.module_descriptor = sys.modules.user_modules[str(self.module_file)][0]
        self.logger = self.reloader.logger

    def disable_pydev_warning(self):
        try:
            import pydevd_tracing
        except ImportError:
            return

        pydevd_tracing.TracingFunctionHolder._warn = False

    def execute(self, dry_run=False) -> None:
        # in some instances module object can't be pre cached
        # for example it's the entrypoint and still executing
        if not self.module_descriptor.module_obj:
            self.module_descriptor.post_execute()

        self.logger.debug("Old module: ")

        self.logger.debug("\n".join(self.module_descriptor.module_obj.get_obj_strs()))
        self.disable_pydev_warning()

        trace = sys.gettrace()
        sys.settrace(None)
        module_python_obj = misc.import_from_file(self.module_descriptor.path, self.reloader.root)
        sys.settrace(trace)

        new_module_descriptor = ModuleDescriptor(reloader=self.reloader,
                                                 name=self.module_descriptor.name,
                                                 path=self.module_descriptor.path,
                                                 body=module_python_obj)
        new_module_descriptor.post_execute()

        self.logger.debug("New module: ")
        self.logger.debug("\n".join(new_module_descriptor.module_obj.get_obj_strs()))

        actions = self.module_descriptor.module_obj.get_actions_for_update(new_module_descriptor.module_obj)
        actions.sort(key=lambda a: a.priority, reverse=True)

        for a in actions:
            if isinstance(a, UpdateModule) and self.reloader.is_already_reloaded(a.module_descriptor):
                continue

            a.pre_execute()
            if not dry_run:
                a.execute()
                a.post_execute()

        sys.modules.user_modules[str(self.module_file)][0] = new_module_descriptor

    def rollback(self) -> None:
        sys.modules.user_modules[str(self.module_file)][0] = self.module_descriptor

    def __repr__(self) -> str:
        return f"Update Module: {self.module_descriptor.name}"


@dataclass(repr=False)
class Module(ContainerObj):
    module_descriptor: "ModuleDescriptor"
    flat: Dict[str, Object] = field(init=False, default_factory=dict)
    python_obj_to_objs: Dict[int, List[Object]] = field(
        init=False, default_factory=lambda: defaultdict(list)
    )

    def __post_init__(self) -> None:
        self.python_obj = self.module_descriptor.body
        self.name = self.module_descriptor.name
        self.parent = None
        self.module = self
        self.collect_children()

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        return False

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return []

    @property
    def file(self) -> Path:
        ret = self.module_descriptor.path
        return ret

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        if name.startswith("__") and name.endswith("__") and name != "__all__":
            return True

        ret = name in __builtins__.keys() or name == "__builtins__"
        return ret

    def get_dict(self) -> "OrderedDict[str, Any]":
        return OrderedDict(self.python_obj.__dict__)

    @classmethod
    def _is_ignored(cls, name: str) -> bool:
        return False

    def is_already_processed(self, obj: "Object") -> bool:
        ret = id(obj) in [id(o.python_obj) for o in self.get_flat_repr().values()]
        return ret

    def register_obj(self, obj: Object) -> None:
        self.flat[obj.full_name] = obj
        self.python_obj_to_objs[id(obj.python_obj)].append(obj)

    def unregister_obj(self, obj: Object) -> None:
        self.flat.pop(obj.full_name)
        self.python_obj_to_objs[id(obj.python_obj)].remove(obj)

    def __repr__(self) -> str:
        return f"Module: {self.module_descriptor.name}"

    def get_obj_strs(self) -> Tuple[str]:
        ret = tuple(f"{k}: {v.get_obj_type_name()}" for k, v in self.flat.items())
        return ret

    def get_flat_repr(self) -> Dict[str, Object]:
        ret = {self.name: self}
        for o in self.children.values():
            ret.update(o.get_flat_repr())

        return ret
