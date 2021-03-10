import ast
import sys
from abc import ABC
from collections import OrderedDict, defaultdict
from functools import lru_cache
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

    @dataclass
    class Node(ABC):
        content: Optional[ast.AST]
        parent: Optional["Source.Node"]

        children: Dict[str, "Source.Node"] = field(init=False, default_factory=dict)
        name: str = field(init=False, default="")

        type: ast.stmt = NotImplemented

        @property
        def fullname(self) -> str:
            return f"{self.parent.fullname}.{self.name}" if self.parent and self.parent.fullname else self.name

        @property
        def body(self) -> List[ast.stmt]:
            return []

        def child_factory(self, ast_node: ast.stmt, parent: Optional["Source.Node"]) -> Optional["Source.Node"]:
            node_type = Source.get_all_node_types().get(type(ast_node), None)
            if not node_type:
                return None
            child = node_type(content=ast_node, parent=parent)
            return child

        def add_to_parent(self, parent: "Source.Node") -> None:
            parent.children[self.name] = self
            self.process()

        def process(self) -> None:
            body = self.body
            if not body:
                return

            for b in self.body:
                child = self.child_factory(b, self)
                if not child:
                    continue

                child.add_to_parent(self)

        def get_flat_syntax(self) -> 'OrderedDict[str, "Source.Node"]':
            flat = OrderedDict()
            for n, c in self.children.items():
                flat[c.fullname] = c
                flat.update(c.get_flat_syntax())

            return flat

        def get_flat_syntax_str(self) -> 'OrderedDict[str, str]':
            ret = OrderedDict()
            flat = self.get_flat_syntax()
            for n, v in flat.items():
                ret[n] = v.get_type_name()

            return ret

        def get_type_name(self) -> str:
            return self.__class__.__name__

    @dataclass
    class Imported(Node):
        types = [None]

    @dataclass
    class Import(Node):
        types = [ast.Import]

        def add_to_parent(self, parent: "Source.Node") -> None:
            for n in self.content.names:
                module = Source.Imported(content=None, parent=parent)
                module.name = n.asname or n.name
                parent.children[module.name] = module

    @dataclass
    class FromImport(Import):
        types = [ast.ImportFrom]

    @dataclass
    class Class(Node):
        types = [ast.ClassDef]

        def __post_init__(self) -> None:
            self.name = self.content.name

        @property
        def body(self) -> List[ast.stmt]:
            return self.content.body

    @dataclass
    class DictType(Node):
        types = [ast.Dict]

        def process(self) -> None:
            for k, v in zip(self.content.keys, self.content.values):
                key = self.child_factory(k, None)
                value = self.child_factory(v, self)
                value.name = key.name
                self.children[key.name] = value
                value.process()

        def __str__(self) -> str:
            return "Dict"

    @dataclass
    class Module(Node):
        types = [ast.Module]

        def __post_init__(self) -> None:
            self.name = ""

        @property
        def body(self) -> List[ast.stmt]:
            return self.content.body

    @dataclass
    class Num(Node):
        types = [ast.Num]

        def __post_init__(self) -> None:
            self.name = self.content.n

    @dataclass
    class NameConstant(Node):
        types = [ast.NameConstant]

        def __post_init__(self) -> None:
            self.name = self.content.value

    @dataclass
    class Str(Node):
        types = [ast.Str]

        def __post_init__(self) -> None:
            self.name = self.content.s

    @dataclass
    class Call(Node):
        types = [ast.Call]

    @dataclass
    class FunctionDef(Node):
        types = [ast.FunctionDef]

        def __post_init__(self) -> None:
            self.name = self.content.name

    @dataclass
    class Lambda(Node):
        types = [ast.Lambda]

    @dataclass
    class Name(Node):
        types = [ast.Name]

        def __post_init__(self) -> None:
            self.name = self.content.id

    @dataclass
    class Attribute(Node):
        types = [ast.Attribute]

    @dataclass
    class Op(Node):
        types = [ast.BinOp, ast.BoolOp, ast.UnaryOp]

    @dataclass
    class AssignPair:
        left: "Source.Node"
        right: "Source.Node"

        def add_to_parent(self, parent: "Source.Node") -> None:
            self.right.name = self.left.name
            parent.children[self.left.name] = self.right
            self.right.process()

    @dataclass
    class Assign(Node):
        types = [ast.Assign]

        def get_targets(self) -> List[ast.stmt]:
            return self.content.targets

        def process_target(self, target: ast.stmt, parent: "Source.Node") -> None:
            target_obj = self.child_factory(target, None)
            if not target_obj:
                return
            value_obj = self.child_factory(self.content.value, parent)

            if isinstance(target_obj, Source.TupleType) and isinstance(value_obj, Source.TupleType):
                zipped = zip(target_obj.body, value_obj.body)
            elif isinstance(target_obj, Source.TupleType):
                zipped = zip(target_obj.body, [value_obj.content] * len(target_obj.body))
            else:
                zipped = [(target_obj.content, value_obj.content)]

            for l, r in zipped:
                left = self.child_factory(l, None)
                right = self.child_factory(r, parent)

                pair = Source.AssignPair(left=left, right=right)
                pair.add_to_parent(parent)

        def add_to_parent(self, parent: "Source.Node") -> None:
            for t in self.get_targets():
                self.process_target(t, parent)

        @property
        def body(self) -> List[ast.stmt]:
            return [self.content.value]

    @dataclass
    class AnnAssign(Assign):
        types = [ast.AnnAssign]

        def get_targets(self) -> List[ast.stmt]:
            if self.content.value:
                return [self.content.target]
            else:
                return []

    @dataclass
    class ListType(Node):
        types = [ast.List]

        def get_type_name(self) -> str:
            return "List"

        def process(self) -> None:
            for i, v in enumerate(self.content.elts):
                value = self.child_factory(v, self)
                value.name = str(i)
                self.children[value.name] = value
                value.process()

    @dataclass
    class TupleType(ListType):
        types = [ast.Tuple]

        @property
        def body(self) -> List[ast.stmt]:
            return self.content.elts

        def get_type_name(self) -> str:
            return "Tuple"

    flat_syntax: 'OrderedDict[str, Node]' = field(init=False)
    flat_syntax_str: 'OrderedDict[str, str]' = field(init=False)
    root_node: Node = field(init=False)

    @classmethod
    @lru_cache(maxsize=None)
    def get_all_node_types(cls) -> Dict[ast.stmt, Type["Source.Node"]]:
        ret = {}

        for k, v in cls.__dict__.items():
            if not isinstance(v, type):
                continue

            if not issubclass(v, Source.Node):
                continue

            if ABC in v.__bases__:
                continue

            for t in v.types:
                ret[t] = v

        return ret

    def __post_init__(self) -> None:
        self.content = self.path.read_text()
        self.syntax = ast.parse(self.content, str(self.path))

        node_types = self.get_all_node_types()
        self.root_node = node_types[type(self.syntax)](content=self.syntax, parent=None)
        self.root_node.process()

        self.flat_syntax = self.root_node.get_flat_syntax()
        self.flat_syntax_str = self.root_node.get_flat_syntax_str()

    def _get_namespaced_name(self, parent: str, name: str) -> str:
        return f"{parent}.{name}" if parent else name


@dataclass(repr=False)
class ModuleDescriptor:
    reloader: "PartialReloader"
    name: str
    path: Path
    body: ModuleType
    source: Source = field(init=False)
    module_obj: "Module" = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.fetch_source()

    def post_execute(self) -> None:
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
        module = ModuleDescriptor(name=key,
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
    priority = 50
    user_modules: List[ModuleDescriptor]
    module_n: int

    logger: Logger = field(init=False)
    _module_descriptor_for_rollback: ModuleDescriptor = field(init=False)

    def __post_init__(self) -> None:
        self._module_descriptor_for_rollback = self.module_descriptor
        self.logger = self.reloader.logger

    @classmethod
    def factory(cls, reloader: "PartialReloader", module_file: Path, dry_run: bool = False) -> List["UpdateModule"]:
        ret = []
        user_modules = sys.modules.user_modules.get(str(module_file), [])

        for i, um in enumerate(user_modules):
            action = UpdateModule(reloader=reloader,
                                  user_modules=user_modules,
                                  module_n=i)
            ret.append(action)

        return ret

    @property
    def module_descriptor(self) -> ModuleDescriptor:
        ret = self.user_modules[self.module_n]
        return ret

    def set_modules_descriptor(self, module_descriptor: ModuleDescriptor) -> None:
        self.module_descriptor_for_rollback = module_descriptor
        self.user_modules[self.module_n] = module_descriptor

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

        self.set_modules_descriptor(ModuleDescriptor(self.reloader,
                                                     name=self.module_descriptor.name,
                                                     path=self.module_descriptor.path,
                                                     body=self.module_descriptor.module_obj.python_obj))
        self.module_descriptor.post_execute()

    def rollback(self) -> None:
        self.set_modules_descriptor(self._module_descriptor_for_rollback)

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
