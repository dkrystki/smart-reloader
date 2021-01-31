import ast
import inspect
import os
import sys
from collections import OrderedDict, defaultdict
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent, indent
from types import ModuleType
from typing import Any, Callable, DefaultDict, Dict, List, Optional, Set, Tuple, Type

from . import dependency_watcher, misc

dataclass = dataclass(repr=False)


__all__ = ["Reloader"]


def equal(a: Any, b: Any) -> bool:
    try:
        return a.__dict__ == b.__dict__
    except AttributeError:
        pass
    try:
        ret = bool(a == b)
    except Exception as e:
        return True

    return ret


equals: Dict[str, Callable] = defaultdict(lambda: equal)
equals["pandas.core.series.Series"] = lambda a, b: a.equals(b)
equals["pandas.core.series.Series"] = lambda a, b: a.equals(b)
equals["pandas.DataFrame"] = lambda a, b: a.equals(b)


class ParentReloadNeeded(Exception):
    pass


@dataclass
class Action:
    reloader: "Reloader"

    def pre_execute(self) -> None:
        self.reloader.applied_actions.append(self)

    def __eq__(self, other: "Action") -> bool:
        raise NotImplementedError()


@dataclass
class Object:
    @dataclass
    class Add(Action):
        parent: "ContainerObj"
        object: "Object"

        def __repr__(self) -> str:
            return f"Add: {repr(self.object)}"

        def execute(self) -> None:
            self.pre_execute()
            setattr(self.parent.python_obj, self.object.name, self.object.python_obj)

    @dataclass
    class Update(Action):
        parent: Optional["ContainerObj"]
        old_object: "Object"
        new_object: Optional["Object"]

        def __repr__(self) -> str:
            return f"Update: {repr(self.old_object)}"

        def execute(self) -> None:
            self.pre_execute()
            python_obj = self.new_object.get_fixed_reference(self.old_object.module)

            setattr(
                self.old_object.parent.python_obj,
                self.old_object.name,
                python_obj,
            )

    @dataclass
    class Delete(Action):
        parent: Optional["ContainerObj"]
        object: "Object"

        def __repr__(self) -> str:
            return f"Delete: {repr(self.object)}"

        def execute(self) -> None:
            self.pre_execute()
            delattr(self.parent.python_obj, self.object.name)

    python_obj: Any
    reloader: "Reloader"
    name: str = ""
    module: Optional["Module"] = None
    parent: Optional["ContainerObj"] = None

    def __post_init__(self) -> None:
        self.module.register_obj(self)

    @property
    def bare_name(self) -> str:
        ret = self.full_name.split(".")[-1]
        return ret

    def get_actions_for_update(self, new_object: "Variable") -> List["Action"]:
        if self.safe_compare(new_object):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                old_object=self,
                new_object=new_object,
            )
        ]

        ret.extend(self.get_actions_for_dependent_modules())
        return ret

    def is_foreign_obj(self, obj: Any) -> bool:
        if hasattr(obj, "__module__") and obj.__module__:
            module_name = (
                obj.__module__.replace(".py", "").replace("/", ".").replace("\\", ".")
            )
            if not module_name.endswith(self.module.name):
                return True

        return False

    def get_fixed_reference(self, module: "Module") -> Any:
        return self.python_obj

    def get_python_obj_from_module(self, obj: Any, module: "Module") -> Optional[Any]:
        matching_objs = self.module.python_obj_to_objs[id(obj)]
        if not matching_objs:
            return None

        obj_from_module = matching_objs[0]
        ret = module.flat[obj_from_module.full_name].python_obj
        return ret

    def get_actions_for_add(
        self, reloader: "Reloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        return [self.Add(reloader=reloader, parent=parent, object=obj)]

    def get_actions_for_delete(
        self, reloader: "Reloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Delete(reloader=reloader, parent=parent, object=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret

    @property
    def full_name(self) -> str:
        return (
            f"{self.parent.full_name}.{self.name}"
            if self.parent and self.parent.name
            else self.name
        )

    @property
    def type(self) -> str:
        try:
            return f"{self.python_obj.__module__}.{self.python_obj.__class__.__name__}"
        except AttributeError:
            return self.python_obj.__class__.__name__

    @classmethod
    def _is_ignored(cls, name: str) -> bool:
        name = str(name)
        if name.startswith("__") and name.endswith("__"):
            return True

        return name in ["None"]

    def safe_compare(self, other: "Object"):
        try:
            return equals[self.type](self.python_obj, other.python_obj)
        except BaseException as e:
            return False

    @property
    def source(self) -> str:
        try:
            ret = inspect.getsource(self.python_obj)
            ret = dedent(ret)
            return ret
        except (TypeError, OSError):
            return ""

    def get_parents_flat(self) -> List["Object"]:
        ret = []

        obj = self
        while obj.parent:
            ret.append(obj.parent)
            obj = obj.parent

        return ret

    def get_parents_obj_flat(self) -> List["Object"]:
        ret = [o.python_obj for o in self.get_parents_flat()]
        return ret

    def get_actions_for_dependent_modules(self) -> List[Action]:
        ret = []

        modules = copy(
            self.reloader.named_obj_to_modules[self.name, id(self.python_obj)]
        )

        potential_indirect_use_modules = copy(
            self.reloader.obj_to_modules[id(self.parent.python_obj)]
        )
        for m in potential_indirect_use_modules:
            if f"{self.parent.bare_name}.{self.name}" not in inspect.getsource(m):
                continue
            modules.add(m)

        if self.module.python_obj in modules:
            modules.remove(self.module.python_obj)

        for m in copy(modules):
            if self.reloader.is_already_reloaded(m) and m in modules:
                modules.remove(m)

        # sort
        modules = list(modules)
        all_modules = list(sys.modules.values())
        modules.sort(key=lambda x: all_modules.index(x))

        for m in modules:
            module = Module(m, reloader=self.reloader)
            ret.append(Module.Update(self.reloader, module))

        return ret

    def is_primitive(self, obj: Any) -> bool:
        if obj is None:
            return True

        ret = any(type(obj) is p for p in [str, bool, int, float])
        return ret

    def __eq__(self, other: "Object") -> bool:
        return self.python_obj == other.python_obj

    def __ne__(self, other: "Object") -> bool:
        return self.python_obj != other.python_obj

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.full_name}"


@dataclass
class FinalObj(Object):
    def get_fixed_reference(self, module: "Module") -> Any:
        python_obj = copy(self.python_obj)
        if not self.is_foreign_obj(self.python_obj) and not self.is_primitive(
            self.python_obj
        ):
            fixed_reference_obj = self.get_python_obj_from_module(
                self.python_obj, module
            )
            python_obj.__class__ = fixed_reference_obj.__class__

        return python_obj


@dataclass
class Reference(FinalObj):
    def get_fixed_reference(self, module: "Module") -> Any:
        ret = self.get_python_obj_from_module(self.python_obj, module)
        return ret


@dataclass
class Function(FinalObj):
    class Update(FinalObj.Update):
        old_object: "Function"
        new_object: Optional["Function"]

        def execute(self) -> None:
            self.pre_execute()
            self.old_object.get_func(
                self.old_object.python_obj
            ).__code__ = self.new_object.get_func(self.new_object.python_obj).__code__

    def get_actions_for_update(self, new_object: "Function") -> List["Action"]:
        if self != new_object:
            return [
                self.Update(
                    reloader=self.reloader,
                    parent=self.parent,
                    old_object=self,
                    new_object=new_object,
                )
            ]
        else:
            return []

    def __eq__(self, other: "Function") -> bool:
        compare_fields = [
            "co_argcount",
            "co_cellvars",
            "co_code",
            "co_consts",
            "co_flags",
            "co_freevars",
            "co_lnotab",
            "co_name",
            "co_names",
            "co_nlocals",
            "co_stacksize",
            "co_varnames",
        ]

        for f in compare_fields:
            if getattr(self.get_func(self.python_obj).__code__, f) != getattr(
                self.get_func(other.python_obj).__code__, f
            ):
                return False

        return True

    def __ne__(self, other: "Function") -> bool:
        return not (Function.__eq__(self, other))

    @property
    def source(self) -> str:
        try:
            ret = inspect.getsource(self.get_func(self.python_obj))
            ret = dedent(ret)
        except (TypeError, OSError):
            return ""

        if (
            isinstance(self.parent, Dictionary)
            and self.python_obj.__name__ == "<lambda>"
        ):
            ret = ret[ret.find(":") + 1 :]
            ret = dedent(ret)

        return ret

    def is_global(self) -> bool:
        ret = self.parent == self.module
        return ret

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj

    @classmethod
    def _is_ignored(cls, name: str) -> bool:
        ret = name in ["__mro_override__", "__update_mro__"]

        return ret


@dataclass
class PropertyGetter(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.fget


class PropertySetter(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.fset


@dataclass
class ContainerObj(Object):
    children: Dict[str, "Object"] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        self._collect_children()

    def get_dict(self) -> Dict[str, Any]:
        raise NotImplementedError()

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        return False

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        if id(obj) in self.module.python_obj_to_objs and not self.is_primitive(obj):
            return {name: Reference}

        if inspect.isclass(obj) and not self.is_foreign_obj(obj):
            return {name: Class}

        if inspect.isfunction(obj):
            return {name: Function}

        if isinstance(obj, dict):
            return {name: Dictionary}

        return {}

    def _collect_children(self) -> None:
        for n, o in self.get_dict().items():
            # break recursions
            if any(o is p for p in self.get_parents_obj_flat() + [self.python_obj]):
                continue

            if self._is_child_ignored(n, o):
                continue

            obj_classes = self._python_obj_to_obj_classes(n, o)

            for n, obj_class in obj_classes.items():
                if obj_class._is_ignored(n):
                    continue
                obj = obj_class(
                    o, parent=self, name=n, reloader=self.reloader, module=self.module
                )
                self.children[n] = obj

    @property
    def source(self) -> str:
        ret = inspect.getsource(self.python_obj)
        for c in self.children.values():
            ret = ret.replace(c.source, "")

        return ret

    def get_actions_for_update(self, new_object: Object) -> List[Action]:
        ret = []

        a = self.children
        b = new_object.children
        new_objects_names = b.keys() - a.keys()
        new_objects = {n: b[n] for n in new_objects_names}
        for o in new_objects.values():
            ret.extend(
                o.get_actions_for_add(reloader=self.reloader, parent=self, obj=o)
            )

        deleted_objects_names = a.keys() - b.keys()
        deleted_objects = {n: a[n] for n in deleted_objects_names}
        for o in deleted_objects.values():
            parent = o.parent
            ret.extend(
                o.get_actions_for_delete(reloader=self.reloader, parent=parent, obj=o)
            )

        for n, o in a.items():
            # if deleted
            if n not in b:
                continue

            if o is self:
                continue

            ret.extend(o.get_actions_for_update(new_object=b[n]))

        return ret


@dataclass
class Class(ContainerObj):
    @dataclass
    class Add(ContainerObj.Add):
        def __repr__(self) -> str:
            return f"Add: {repr(self.object)}"

        def execute(self) -> None:
            self.pre_execute()
            exec(self.object.source, self.parent.module.python_obj.__dict__)

    def get_actions_for_update(self, new_object: "Class") -> List["Action"]:
        if str(self.python_obj.__mro__) == str(new_object.python_obj.__mro__):
            try:
                return super().get_actions_for_update(new_object)
            except ParentReloadNeeded:
                return self.get_full_reload_actions()
        else:
            return self.get_full_reload_actions()

    def get_full_reload_actions(self) -> List[Action]:
        return [
            *self.get_actions_for_delete(self.reloader, self.parent, self),
            *self.get_actions_for_add(self.reloader, self.parent, self),
            *self.get_actions_for_dependent_modules(),
        ]

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        return False

    def get_dict(self) -> Dict[str, Any]:
        ret = self.python_obj.__dict__
        return ret

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        # If already process means it's just a reference
        if id(obj) in self.module.python_obj_to_objs and not self.is_primitive(obj):
            return {name: Reference}

        if inspect.ismethoddescriptor(obj):
            return {name: ClassMethod}

        if inspect.isfunction(obj):
            return {name: Method}

        ret = super()._python_obj_to_obj_classes(name, obj)
        if ret:
            return ret

        if isinstance(obj, property):
            ret = {name: PropertyGetter}

            if obj.fset:
                setter_name = name + "__setter__"
                ret[setter_name] = PropertySetter
            return ret

        return {name: ClassVariable}

    def get_actions_for_add(
        self, reloader: "Reloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Add(reloader=reloader, parent=parent, object=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass
class Method(Function):
    @dataclass
    class Add(Function.Add):
        def execute(self) -> None:
            super().execute()

    class Update(Function.Update):
        def execute(self) -> None:
            self.pre_execute()
            self.old_object.get_func(
                self.old_object.python_obj
            ).__code__ = self.new_object.get_func(self.new_object.python_obj).__code__

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj

    def get_actions_for_add(
        self, reloader: "Reloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        if hasattr(parent.python_obj, self.name):
            if (
                getattr(parent.python_obj, self.name).__code__.co_freevars
                != obj.python_obj.__code__.co_freevars
            ):
                raise ParentReloadNeeded()

        return super().get_actions_for_add(reloader, parent, obj)


@dataclass
class ClassMethod(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.__func__


@dataclass
class Dictionary(ContainerObj):
    def get_dict(self) -> Dict[str, Any]:
        return self.python_obj

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        if isinstance(obj, dict):
            return {name: Dictionary}

        return {name: DictionaryItem}


@dataclass
class Variable(FinalObj):
    def get_actions_for_add(
        self, reloader: "Reloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Add(reloader=reloader, parent=parent, object=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass
class ClassVariable(Variable):
    def get_actions_for_update(self, new_object: "Variable") -> List["Action"]:
        if self.safe_compare(new_object):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                old_object=self,
                new_object=new_object,
            )
        ]

        if isinstance(self.parent.parent, Module):
            ret.extend(self.get_actions_for_dependent_modules())
        return ret

    @classmethod
    def _is_ignored(cls, name: str) -> bool:
        if name.startswith("__") and name.endswith("__"):
            return True

        ret = name in [
            "_abc_generic_negative_cache",
            "_abc_registry",
            "_abc_cache",
        ]

        return ret


@dataclass
class DictionaryItem(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            self.pre_execute()
            self.parent.python_obj[self.object.name] = copy(self.object.python_obj)

    class Update(FinalObj.Update):
        def execute(self) -> None:
            self.pre_execute()
            self.old_object.parent.python_obj[
                self.new_object.name
            ] = self.new_object.python_obj

    class Delete(FinalObj.Delete):
        parent: Optional["ContainerObj"]
        object: "Object"

        def execute(self) -> None:
            self.pre_execute()
            del self.parent.python_obj[self.object.name]

    def get_actions_for_update(self, new_object: "Variable") -> List["Action"]:

        if self.safe_compare(new_object):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                old_object=self,
                new_object=new_object,
            )
        ]

        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass
class Import(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            self.pre_execute()
            module = sys.modules.get(self.object.name, self.object.python_obj)
            setattr(self.parent.python_obj, self.object.name, module)

    def get_actions_for_update(self, new_object: "Variable") -> List["Action"]:
        return []

    def get_actions_for_add(
        self, reloader: "Reloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Add(reloader=reloader, parent=parent, object=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret

    def get_actions_for_delete(
        self, reloader: "Reloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        return []


@dataclass
class Module(ContainerObj):
    flat: Dict[str, Object] = field(init=False, default_factory=dict)
    python_obj_to_objs: Dict[int, List[Object]] = field(
        init=False, default_factory=lambda: defaultdict(list)
    )

    @dataclass
    class Update(Action):
        module: "Module"

        def execute(self) -> None:
            if self.reloader.is_already_reloaded(self.module.python_obj):
                return
            self.reloader.reload(self.module.python_obj)

        def __repr__(self) -> str:
            return f"Update: {repr(self.module)}"

    def __post_init__(self) -> None:
        self.module = self
        super().__post_init__()

    @property
    def file(self) -> Path:
        ret = Path(self.python_obj.__file__)
        return ret

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        ret = super()._python_obj_to_obj_classes(name, obj)
        if ret:
            return ret

        if inspect.ismodule(obj):
            return {name: Import}

        return {name: Variable}

    def get_dict(self) -> Dict[str, Any]:
        return self.python_obj.__dict__

    @classmethod
    def _is_ignored(cls, name: str) -> bool:
        return False

    @property
    def final_objs(self) -> List[FinalObj]:
        """
        Return non container objects
        """
        ret = []
        for o in self.children:
            if not isinstance(o, FinalObj):
                continue
            ret.append(o)
        return ret

    def register_obj(self, obj: Object) -> None:
        self.flat[obj.full_name] = obj
        self.python_obj_to_objs[id(obj.python_obj)].append(obj)

    def __repr__(self) -> str:
        return f"Module: {self.python_obj.__name__}"


@dataclass
class Dependency:
    module_file: Path
    objects: Set[Tuple[str, int]]  # name, id


class Reloader:
    logger: Any
    named_obj_to_modules: DefaultDict[Tuple[str, int], Set[ModuleType]]

    def __init__(self, root: Path, logger: Any) -> None:
        logger.debug(f"Creating partial reloader for {root}")
        self.root = root.resolve()
        self.logger = logger

        self.named_obj_to_modules = defaultdict(set)
        self.obj_to_modules = defaultdict(set)
        self.applied_actions = []

        self._collect_all_dependencies()

    def get_new_module(self, old_module: Module) -> Module:
        module_obj = misc.import_from_file(old_module.file, self.root)

        return Module(
            module_obj,
            reloader=self,
            name=old_module.name,
        )

    def is_already_reloaded(self, module: ModuleType) -> bool:
        for a in [a for a in self.applied_actions if isinstance(a, Module.Update)]:
            if a.module.python_obj is module:
                return True

    def get_actions(self, module_file: str) -> List[Action]:
        actions = []
        module_objs = dependency_watcher.path_to_modules[module_file]

        for m in module_objs:
            old_module = Module(m, reloader=self, name=f"{m.__name__}")
            self.applied_actions.append(Module.Update(self, old_module))

            new_module = self.get_new_module(old_module)
            actions.extend(old_module.get_actions_for_update(new_module))
        return actions

    def _collect_dependencies(self, module: ModuleType) -> None:
        for n, o in module.__dict__.items():
            if n.startswith("__") and n.endswith("__"):
                continue
            self.named_obj_to_modules[(n, id(o))].add(module)
            self.obj_to_modules[id(o)].add(module)

    def _collect_all_dependencies(self) -> None:
        for p, modules in copy(dependency_watcher.path_to_modules).items():
            if self.root not in Path(p).parents:
                continue
            for m in list(modules):
                self._collect_dependencies(m)

    def reload(self, module_file: str) -> List[Action]:
        """
        :return: True if succeded False i unable to reload
        """

        for a in self.get_actions(module_file):
            a.execute()

        return self.applied_actions
