import ast
import inspect
import os
import re
import sys
from collections import OrderedDict, defaultdict
from copy import copy
from threading import Thread
from time import sleep

from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from textwrap import dedent, indent
from types import CodeType, ModuleType
from typing import (
    Any,
    Callable,
    ClassVar,
    DefaultDict,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
)

from deepdiff import DeepDiff

from . import console, dependency_watcher, misc

dataclass = dataclass(repr=False)


__all__ = ["PartialReloader", "FullReloadNeeded"]


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


class FullReloadNeeded(Exception):
    pass


@dataclass
class Action:
    object: "Object"
    reloader: "PartialReloader"
    priority: ClassVar[int] = field(init=False, default=100)

    def log(self) -> None:
        self.reloader.logger.info(str(self))

    def pre_execute(self) -> None:
        self.reloader.applied_actions.append(self)
        self.log()

    def rollback(self) -> None:
        pass

    def __eq__(self, other: "Action") -> bool:
        raise NotImplementedError()

    def execute(self) -> None:
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
            self.parent.set_attr(self.object.name, self.object.python_obj)

        def rollback(self) -> None:
            super().rollback()
            self.parent.del_attr(self.object.name)

    @dataclass
    class Update(Action):
        parent: Optional["ContainerObj"]
        object: "Object"
        new_object: Optional["Object"]
        difference: dict = field(init=False)

        def __repr__(self) -> str:
            return f"Update: {repr(self.object)}"

        def execute(self) -> None:
            self.pre_execute()
            python_obj = self.new_object.get_fixed_reference(self.object.module)

            self.object.parent.set_attr(self.object.name, python_obj)

        def rollback(self) -> None:
            super().rollback()
            self.object.parent.set_attr(self.object.name, self.object.python_obj)

    @dataclass
    class Delete(Action):
        parent: Optional["ContainerObj"]
        object: "Object"

        def __repr__(self) -> str:
            return f"Delete: {repr(self.object)}"

        def execute(self) -> None:
            self.pre_execute()
            self.parent.del_attr(self.object.name)

        def rollback(self) -> None:
            super().rollback()
            self.parent.set_attr(self.object.name, self.object.python_obj)

    @dataclass
    class Rollback(Action):
        action: Action

        def __repr__(self) -> str:
            return f"Rollback: {repr(self.action)}"

        def execute(self) -> None:
            self.pre_execute()
            self.action.rollback()

    python_obj: Any
    reloader: "PartialReloader"
    name: str = ""
    module: Optional["Module"] = None
    parent: Optional["ContainerObj"] = None

    def __post_init__(self) -> None:
        self.module.register_obj(self)

    @property
    def bare_name(self) -> str:
        ret = self.full_name.split(".")[-1]
        return ret

    def get_actions_for_update(self, new_object: "Object") -> List["Action"]:
        if self.safe_compare(new_object):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                object=self,
                new_object=new_object,
            )
        ]

        if not self.is_foreign_obj(self.python_obj):
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
        obj = module.flat.get(obj_from_module.full_name, None)
        if not obj:
            return None
        return obj.python_obj

    def get_actions_for_add(
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Add(reloader=reloader, parent=parent, object=obj)]
        if self.is_in_all():
            ret.extend(self.get_star_import_updates_actions())
        return ret

    def is_in_all(self) -> bool:
        if self.bare_name == "__all__":
            return True

        ret = not hasattr(self.module.python_obj, "__all__") or self.bare_name in self.module.python_obj.__all__
        return ret

    def get_actions_for_delete(
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Delete(reloader=reloader, parent=parent, object=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        if self.is_in_all():
            ret.extend(self.get_star_import_updates_actions())
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
        if name == "__all__":
            return False

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
            if (
                f"{self.parent.bare_name}.{self.name}"
                not in Path(m.__file__).read_text()
            ):
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
            ret.append(Module.Update(reloader=self.reloader, object=module))

        return ret

    def is_primitive(self, obj: Any) -> bool:
        if obj is None:
            return True

        ret = any(
            type(obj) is p or obj is p
            for p in [str, bool, int, float, list, dict, tuple, set]
        )
        return ret

    def __eq__(self, other: "Object") -> bool:
        return self.python_obj == other.python_obj

    def __ne__(self, other: "Object") -> bool:
        return self.python_obj != other.python_obj

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.full_name}"

    def get_flat_repr(self) -> Dict[str, "Object"]:
        return {self.full_name: self}

    def get_star_import_updates_actions(self) -> List[Action]:
        ret = []
        star_import_modules = dependency_watcher.module_file_to_start_import_usages[
            str(self.module.file)
        ]

        for module_path in star_import_modules:
            modules = self.reloader.modules.user_modules[module_path]

            for m in modules:
                module = Module(m, reloader=self.reloader)
                ret.append(Module.Update(reloader=self.reloader, object=module))

        return ret


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
            if not self.is_primitive(python_obj):
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
        object: "Function"
        new_object: Optional["Function"]

        def execute(self) -> None:
            self.pre_execute()
            self.object.get_func(
                self.object.python_obj
            ).__code__ = self.new_object.get_func(self.new_object.python_obj).__code__

    def get_actions_for_update(self, new_object: "Function") -> List["Action"]:
        if self != new_object:
            return [
                self.Update(
                    reloader=self.reloader,
                    parent=self.parent,
                    object=self,
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

    def get_dict(self) -> "OrderedDict[str, Any]":
        raise NotImplementedError()

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        return False

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        if id(obj) in self.module.python_obj_to_objs and not self.is_primitive(obj):
            return {name: Reference}

        if inspect.isclass(obj) and not self.is_foreign_obj(obj):
            # if the name is different that the class name it means it's just a reference not actualy class definition
            if name != obj.__name__:
                return {name: Reference}
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

            if not obj_classes:
                continue

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

    def set_attr(self, name: str, obj: "Any") -> None:
        setattr(self.python_obj, name, obj)

    def del_attr(self, name: str) -> None:
        delattr(self.python_obj, name)

    def get_flat_repr(self) -> Dict[str, Object]:
        ret = {}
        for o in self.children.values():
            ret.update(o.get_flat_repr())

        ret.update({self.full_name: self})

        return ret


@dataclass
class Class(ContainerObj):
    @dataclass
    class Add(ContainerObj.Add):
        def __repr__(self) -> str:
            return f"Add: {repr(self.object)}"

        def execute(self) -> None:
            self.pre_execute()
            source = dedent(self.object.source)

            if isinstance(self.parent, Class):
                context = dict(self.parent.python_obj.__dict__)
                exec(source, self.parent.module.python_obj.__dict__, context)
                self.parent.set_attr(self.object.name, context[self.object.name])
            else:
                exec(source, self.parent.module.python_obj.__dict__)

    def __post_init__(self):
        super().__post_init__()

    def get_actions_for_update(self, new_object: "Class") -> List["Action"]:
        if str(self.python_obj.__mro__) == str(new_object.python_obj.__mro__):
            return super().get_actions_for_update(new_object)
        else:
            raise FullReloadNeeded()

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        return False

    def get_dict(self) -> "OrderedDict[str, Any]":
        # members = inspect.getmembers(self.python_obj)
        # ret = OrderedDict(sorted(members))
        ret = OrderedDict(self.python_obj.__dict__)

        return ret

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        # Don't add objects not defined in base class
        # if hasattr(obj, "__qualname__") and obj.__qualname__.split(".")[0] != self.python_obj.__name__:
        #     return {}

        # If already process means it's just a reference
        if id(obj) in self.reloader.obj_to_modules and not self.is_primitive(obj):
            return {name: Reference}

        if isinstance(obj, classmethod):
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
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Add(reloader=reloader, parent=parent, object=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass
class Method(Function):
    @dataclass
    class Add(Function.Add):
        object: "Method"
        parent: "Class"

        def execute(self) -> None:
            self.pre_execute()
            fun = self.object.get_fixed_fun(self.object.python_obj, self.parent)
            fun.__code__ = self.object.get_code_with_source_file_info(fun, self.object)
            setattr(self.parent.python_obj, self.object.name, fun)

    class Update(Function.Update):
        object: "Method"
        new_object: Optional["Method"]
        parent: "Class"

        def execute(self) -> None:
            self.pre_execute()
            fun = self.object.get_fixed_fun(self.new_object.python_obj, self.parent)
            code = self.object.get_code_with_source_file_info(fun, self.new_object)
            self.object.python_obj.__code__ = code

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj

    def get_fixed_fun(self, fun: Callable, parent_class: Class) -> Callable:
        source = dedent(inspect.getsource(fun))
        source = re.sub(r"super\(\s*\)", f"super({parent_class.name}, self)", source)
        source = indent(source, "    " * 4)

        builder = dedent(
            f"""
            def builder():
                __class__ = {parent_class.name}\n{source}
                return {self.name}
            """
        )

        context = dict(parent_class.module.python_obj.__dict__)
        exec(builder, context)

        fixed_fun = context["builder"]()
        return fixed_fun

    def get_code_with_source_file_info(
        self, fun: Any, new_object: "Method"
    ) -> CodeType:
        code = CodeType(
            fun.__code__.co_argcount,  # integer
            fun.__code__.co_kwonlyargcount,  # integer
            fun.__code__.co_nlocals,  # integer
            fun.__code__.co_stacksize,  # integer
            fun.__code__.co_flags,  # integer
            fun.__code__.co_code,  # bytes
            fun.__code__.co_consts,  # tuple
            fun.__code__.co_names,  # tuple
            fun.__code__.co_varnames,  # tuple
            self.python_obj.__code__.co_filename,  # string
            fun.__code__.co_name,  # string
            new_object.python_obj.__code__.co_firstlineno,  # integer
            new_object.python_obj.__code__.co_lnotab,  # bytes
            self.python_obj.__code__.co_freevars,  # tuple
            fun.__code__.co_cellvars,  # tuple
        )
        return code


@dataclass
class ClassMethod(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.__func__


@dataclass
class Dictionary(ContainerObj):
    def get_dict(self) -> "OrderedDict[str, Any]":
        return self.python_obj

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        if isinstance(obj, dict):
            return {name: Dictionary}

        return {name: DictionaryItem}

    def set_attr(self, name: str, obj: "Any") -> None:
        self.python_obj[name] = obj

    def del_attr(self, name: str) -> None:
        del self.python_obj[name]


@dataclass
class Variable(FinalObj):
    pass


@dataclass
class All(FinalObj):
    def get_actions_for_update(self, new_object: "All") -> List["Action"]:
        if new_object.python_obj == self.python_obj:
            return []
        ret = [self.Update(
            reloader=self.reloader,
            parent=self.parent,
            object=self,
            new_object=new_object,
        )]
        ret.extend(self.get_star_import_updates_actions())
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
                object=self,
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
    def get_actions_for_update(self, new_object: "Variable") -> List["Action"]:

        if self.safe_compare(new_object):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                object=self,
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
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["Action"]:
        ret = [self.Add(reloader=reloader, parent=parent, object=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret

    def get_actions_for_delete(
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
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
        priority = 50

        def execute(self) -> None:
            if self.reloader.is_already_reloaded(self.object.python_obj):
                return

            self.reloader._reload(self.object.file)

        def __repr__(self) -> str:
            return f"Update: {repr(self.object)}"

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
        if name == "__all__":
            return {name: All}

        ret = super()._python_obj_to_obj_classes(name, obj)
        if ret:
            return ret

        if inspect.ismodule(obj):
            return {name: Import}

        return {name: Variable}

    def get_dict(self) -> "OrderedDict[str, Any]":
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

    def get_flat_repr(self) -> Dict[str, Object]:
        ret = {self.name: self}
        for o in self.children.values():
            ret.update(o.get_flat_repr())

        return ret


@dataclass
class Dependency:
    module_file: Path
    objects: Set[Tuple[str, int]]  # name, id


class Modules(dict):
    user_modules: DefaultDict[str, List[ModuleType]]

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

        self.user_modules[value.__file__].append(value)

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


@dataclass
class TrickyTypes:
    reloader: "PartialReloader"
    modules: Modules = field(init=False)
    runner: Thread = field(init=False)
    tricky_types: List[type] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.user_modules = self.reloader.modules.user_modules
        self.runner = Thread(target=self._run)

    def start(self):
        self.runner.start()

    def _run(self) -> None:
        self.tricky_types = []

        # wait until importing is done
        while dependency_watcher.seconds_from_last_import() <= 1.0:
            sleep(0.1)

        for m in self.user_modules.keys():
            self.collect_diffs_from_module(Path(m))

    def python_obj_to_dict(self, obj, classkey=None):
        if isinstance(obj, type):
            return obj

        if isinstance(obj, dict):
            data = {}
            for (k, v) in obj.items():
                data[k] = self.python_obj_to_dict(v, classkey)
            return data
        elif hasattr(obj, "_ast"):
            return self.python_obj_to_dict(obj._ast())
        elif hasattr(obj, "__iter__") and not isinstance(obj, str):
            return [self.python_obj_to_dict(v, classkey) for v in obj]
        elif hasattr(obj, "__dict__"):
            data = dict([(key, self.python_obj_to_dict(value, classkey))
                         for key, value in dict(inspect.getmembers(obj)).items()
                         if not callable(value)])
            if classkey is not None and hasattr(obj, "__class__"):
                data[classkey] = obj.__class__.__name__
            return data
        else:
            return obj

    def wait_until_finished(self) -> None:
        while not self.finished():
            sleep(0.1)

    def finished(self) -> bool:
        ret = not self.runner.is_alive()
        return ret

    def collect_diffs_from_module(self, module_file: Path) -> None:
        actions = self.reloader.get_actions(module_file)
        update_actions = [a for a in actions if isinstance(a, Object.Update)]

        for a in update_actions:
            left = self.python_obj_to_dict(a.object.python_obj)
            right = self.python_obj_to_dict(a.new_object.python_obj)
            pass


@dataclass
class PartialReloader:
    root: Path
    logger: Logger
    named_obj_to_modules: DefaultDict[Tuple[str, int], Set[ModuleType]] = field(init=False,
                                                                                default_factory=lambda: defaultdict(set))
    obj_to_modules: DefaultDict[int, Set[ModuleType]] = field(init=False,
                                                              default_factory=lambda: defaultdict(set))
    applied_actions: List[Action] = field(init=False, default_factory=list)
    modules: Modules = field(init=False)
    tricky_types: TrickyTypes = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.logger.debug(f"Creating partial reloader for {self.root}")

        self.modules = Modules(self, sys.modules)
        sys.modules = self.modules
        self.tricky_types = TrickyTypes(reloader=self)
        self.tricky_types.start()

    def _reset(self) -> None:
        self.named_obj_to_modules = defaultdict(set)
        self.obj_to_modules = defaultdict(set)
        self.applied_actions = []

    def get_new_module(self, old_module: Module) -> Module:
        trace = sys.gettrace()
        sys.settrace(None)
        module_obj = misc.import_from_file(old_module.file, self.root)
        sys.settrace(trace)

        return Module(
            module_obj,
            reloader=self,
            name=old_module.name,
        )

    def is_already_reloaded(self, module: ModuleType) -> bool:
        module_update_actions = [
            a for a in self.applied_actions if isinstance(a, Module.Update)
        ]
        for a in module_update_actions:
            if a.object.python_obj is module:
                return True

    def get_actions(self, module_file: Path) -> List[Action]:
        actions = []
        module_objs = self.modules.user_modules[str(module_file)]

        for m in module_objs:
            old_module = Module(python_obj=m, reloader=self, name=f"{m.__name__}")
            action = Module.Update(reloader=self, object=old_module)
            action.log()
            self.applied_actions.append(action)

            new_module = self.get_new_module(old_module)
            actions.extend(old_module.get_actions_for_update(new_module))

        actions.sort(key=lambda a: a.priority, reverse=True)
        return actions

    def _collect_dependencies(self, module: ModuleType) -> None:
        for n, o in module.__dict__.items():
            if n.startswith("__") and n.endswith("__"):
                continue
            self.named_obj_to_modules[(n, id(o))].add(module)
            self.obj_to_modules[id(o)].add(module)

    def _collect_all_dependencies(self) -> None:
        for p, modules in copy(self.modules.user_modules).items():
            if self.root not in Path(p).parents:
                continue
            for m in list(modules):
                self._collect_dependencies(m)

        # remove owner modules (original definition place)
        for key, modules in self.named_obj_to_modules.copy().items():
            sorted_modules = sorted(
                list(modules),
                key=lambda m: list(self.modules.user_modules.keys()).index(m.__file__),
            )
            if sorted_modules:
                sorted_modules.pop(0)
            self.named_obj_to_modules[key] = set(sorted_modules)

        for o_id, modules in self.obj_to_modules.copy().items():
            sorted_modules = sorted(
                list(modules),
                key=lambda m: list(self.modules.user_modules.keys()).index(m.__file__),
            )
            if sorted_modules:
                sorted_modules.pop(0)

            self.obj_to_modules[o_id] = set(sorted_modules)
        pass

    def _reload(self, module_file: Path) -> None:
        actions = self.get_actions(module_file)
        for a in actions:
            a.execute()

    def reload(self, module_file: Path) -> None:
        """
        :return: True if succeded False i unable to reload
        """
        self._reset()

        self._collect_all_dependencies()

        self._reload(module_file)

    def rollback(self) -> None:
        rollback_actions = [
            a.object.Rollback(reloader=self, action=a, object=a.object)
            for a in reversed(self.applied_actions)
        ]

        for a in rollback_actions:
            a.execute()

