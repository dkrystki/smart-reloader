import ast
import ctypes
import inspect
import os
import gc
import ast
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
from types import CodeType, ModuleType, FrameType, FunctionType
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
class BaseAction:
    reloader: "PartialReloader"
    priority: ClassVar[int] = field(init=False, default=100)

    def log(self) -> None:
        self.reloader.logger.info(str(self))

    def rollback(self) -> None:
        pass

    def equal(self, other: "BaseAction") -> bool:
        raise NotImplementedError()

    def execute(self) -> None:
        raise NotImplementedError()

    def pre_execute(self) -> None:
        self.reloader.applied_actions.append(self)
        self.log()


@dataclass
class Action(BaseAction):
    obj: "Object"


@dataclass
class Object:
    @dataclass
    class Add(Action):
        parent: "ContainerObj"
        obj: "Object"

        def __repr__(self) -> str:
            return f"Add: {repr(self.obj)}"

        def execute(self) -> None:
            self.pre_execute()
            self.parent.set_attr(self.obj.name, self.obj.python_obj)

        def rollback(self) -> None:
            super().rollback()
            self.parent.del_attr(self.obj.name)

    @dataclass
    class Update(Action):
        parent: Optional["ContainerObj"]
        obj: "Object"
        new_obj: Optional["Object"]

        def __repr__(self) -> str:
            return f"Update: {repr(self.obj)}"

        def execute(self) -> None:
            self.pre_execute()
            python_obj = self.new_obj.get_fixed_reference(self.obj.module)

            self.obj.parent.set_attr(self.obj.name, python_obj)

        def rollback(self) -> None:
            super().rollback()
            self.obj.parent.set_attr(self.obj.name, self.obj.python_obj)

    @dataclass
    class DeepUpdate(Action):
        parent: Optional["ContainerObj"]
        obj: "Object"
        new_obj: Optional["Object"]
        referrers: List[object] = field(init=False)

        def __post_init__(self):
            pass

        def get_referrers(self, obj: object) -> List[object]:
            ret = []
            referres = gc.get_referrers(obj)
            for r in referres:
                if r is self.obj.__dict__ or r is locals():
                    continue

                ret.append(r)
            return ret

        def __repr__(self) -> str:
            return f"DeepUpdate: {repr(self.obj)}"

        def execute(self) -> None:
            self.pre_execute()

        def rollback(self) -> None:
            super().rollback()


    @dataclass
    class Delete(Action):
        parent: Optional["ContainerObj"]
        obj: "Object"

        def __repr__(self) -> str:
            return f"Delete: {repr(self.obj)}"

        def execute(self) -> None:
            self.pre_execute()
            self.parent.del_attr(self.obj.name)

        def rollback(self) -> None:
            super().rollback()
            self.parent.set_attr(self.obj.name, self.obj.python_obj)

    python_obj: Any
    reloader: "PartialReloader"
    name: Optional[str]
    module: Optional["Module"]
    parent: Optional["ContainerObj"]

    def __post_init__(self) -> None:
        self.module.register_obj(self)

    @property
    def bare_name(self) -> str:
        ret = self.full_name.split(".")[-1]
        return ret

    def get_actions_for_update(self, new_obj: "Object") -> List["BaseAction"]:
        if self.safe_compare(new_obj):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                obj=self,
                new_obj=new_obj,
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
    ) -> List["BaseAction"]:
        ret = [self.Add(reloader=reloader, parent=parent, obj=obj)]
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
    ) -> List["BaseAction"]:
        ret = [self.Delete(reloader=reloader, parent=parent, obj=obj)]
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
    def full_name_without_module_name(self) -> str:
        ret = self.full_name[len(self.module.full_name):]
        ret = ret.lstrip(".")
        return ret

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

    def get_actions_for_dependent_modules(self) -> List[BaseAction]:
        ret = []

        module_descrs = copy(
            self.reloader.named_obj_to_modules[self.name, id(self.python_obj)]
        )

        potential_indirect_use_modules = copy(
            self.reloader.obj_to_modules[id(self.parent.python_obj)]
        )
        for m_descr in potential_indirect_use_modules:
            if (
                f"{self.parent.bare_name}.{self.name}"
                not in m_descr.source.content
            ):
                continue
            module_descrs.add(m_descr)

        if self.module.python_obj in module_descrs:
            module_descrs.remove(self.module.python_obj)

        # sort
        module_descrs = list(module_descrs)
        module_descrs = sorted(module_descrs, key=lambda x: dependency_watcher.import_order.index(str(x.path)))

        for m_descr in module_descrs:
            ret.append(UpdateModule(reloader=self.reloader, module_file=m_descr.path))

        return ret

    def is_primitive(self, obj: Any) -> bool:
        if obj is None:
            return True

        ret = any(
            type(obj) is p or obj is p
            for p in [str, bool, int, float, list, dict, tuple, set]
        )
        return ret

    def equal(self, other: "Object") -> bool:
        return self.python_obj == other.python_obj

    def not_equal(self, other: "Object") -> bool:
        return self.python_obj != other.python_obj

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.full_name}"

    def get_flat_repr(self) -> Dict[str, "Object"]:
        return {self.full_name: self}

    def get_star_import_updates_actions(self) -> List[BaseAction]:
        ret = []
        star_import_modules = dependency_watcher.module_file_to_start_import_usages[
            str(self.module.file)
        ]

        for module_path in star_import_modules:
            modules = self.reloader.modules.user_modules[module_path]

            for m in modules:
                ret.append(UpdateModule(reloader=self.reloader, module_file=m.path))

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
        obj: "Function"
        new_obj: Optional["Function"]
        old_code: CodeType = field(init=False)

        def execute(self) -> None:
            self.pre_execute()
            self.old_code = self.obj.get_func(
                self.obj.python_obj
            ).__code__

            self.obj.get_func(
                self.obj.python_obj
            ).__code__ = self.new_obj.get_func(self.new_obj.python_obj).__code__

        def rollback(self) -> None:
            super().rollback()
            self.obj.get_func(self.obj.python_obj).__code__ = self.old_code

    @dataclass
    class DeepUpdate(FinalObj.DeepUpdate):
        parent: Optional["ContainerObj"]
        obj: "Object"
        new_obj: Optional["Object"]
        referrers: List[object] = field(init=False)

        @dataclass
        class RollabackOperation:
            dict_obj: Any
            dictionary: dict
            key: str
            value: object
            owner: "DeepUpdate"

            def execute(self) -> None:
                self.dictionary[self.key] = self.value
                if inspect.isframe(self.dict_obj):
                    self.owner.apply_changes_to_frame(self.dict_obj)

        rollback_operations: List[RollabackOperation] = field(init=False, default_factory=list)

        def replace_obj(self, what: object, to_what: object):
            referrers = self.get_referrers(what)

            for r in referrers:
                if r is locals():
                    continue

                if isinstance(r, dict):
                    dictionary = r

                elif inspect.isframe(r):
                    if r.f_code.co_filename == __file__:
                        continue
                    dictionary = r.f_locals
                else:
                    continue

                for k, v in dictionary.items():
                    if hasattr(v, "__func__") and v.__func__ is what:
                        dictionary[k] = to_what
                        self.rollback_operations.append(self.RollabackOperation(r, dictionary, k, v, self))

                    if v is what:
                        dictionary[k] = to_what
                        self.rollback_operations.append(self.RollabackOperation(r, dictionary, k, v, self))

                # update frame
                if inspect.isframe(r):
                    self.apply_changes_to_frame(r)

        def apply_changes_to_frame(self, frame_obj: FrameType):
            if inspect.isframe(frame_obj):
                ctypes.pythonapi.PyFrame_LocalsToFast(
                    ctypes.py_object(frame_obj),
                    ctypes.c_int(1))

        def execute(self) -> None:
            self.pre_execute()

            self.replace_obj(self.obj.python_obj, self.new_obj.python_obj)
            if hasattr(self.obj.python_obj, "__func__"):
                self.replace_obj(self.obj.python_obj.__func__, self.new_obj.python_obj)

        def rollback(self) -> None:
            super().rollback()

            for o in self.rollback_operations:
                o.execute()

    def get_actions_for_update(self, new_obj: "Function") -> List["BaseAction"]:
        if type(self.python_obj) != type(new_obj.python_obj) or self.python_obj.__closure__ or new_obj.python_obj.__closure__:
            return [
                self.DeepUpdate(
                    reloader=self.reloader,
                    parent=self.parent,
                    obj=self,
                    new_obj=new_obj,
                )
            ]

        if self.not_equal(new_obj):
            return [
                self.Update(
                    reloader=self.reloader,
                    parent=self.parent,
                    obj=self,
                    new_obj=new_obj,
                )
            ]
        else:
            return []

    def compare_codes(self, left: CodeType, right: CodeType) -> bool:
        compare_fields = [
            "co_argcount",
            "co_cellvars",
            "co_code",
            "co_freevars",
            "co_lnotab",
            "co_name",
            "co_names",
            "co_nlocals",
            "co_varnames",
        ]
        for f in compare_fields:
            if getattr(left, f) != getattr(right, f):
                return False

        if len(left.co_consts) != len(right.co_consts):
            return False

        for left_f, right_f in zip(left.co_consts, right.co_consts):
            if type(left_f) is not type(right_f):
                return False

            if inspect.iscode(left_f):
                if not self.compare_codes(left_f, right_f):
                    return False
            elif left_f != right_f:
                return False

        return True

    def equal(self, other: "Function") -> bool:
        ret = self.source == other.source
        return ret

    def not_equal(self, other: "Function") -> bool:
        return not (self.__class__.equal(self, other))

    def _extract_wrapped(self, decorated: FunctionType):
        closure = (c.cell_contents for c in decorated.__closure__)
        ret = next((c for c in closure if isinstance(c, FunctionType)), None)
        return ret

    @property
    def source(self) -> str:
        func = self.get_func(self.python_obj)
        if func.__closure__:
            target = self._extract_wrapped(func) or func
        else:
            target = func

        source_lines = self.module.module_descriptor.source.content.splitlines(keepends=True)
        lnum = target.__code__.co_firstlineno - 1

        ret = inspect.getblock(source_lines[lnum:])
        ret = "".join(ret)

        ret = dedent(ret)
        return ret

    # @property
    # def source(self) -> str:
    #     try:
    #         ret = inspect.getsource(self.get_func(self.python_obj))
    #         ret = dedent(ret)
    #     except (TypeError, OSError):
    #         return ""
    #
    #     if (
    #         isinstance(self.parent, Dictionary)
    #         and self.python_obj.__name__ == "<lambda>"
    #     ):
    #         ret = ret[ret.find(":") + 1 :]
    #         ret = dedent(ret)
    #
    #     return ret

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

    def equal(self, other: "Function") -> bool:
        return super().equal(other)


class PropertySetter(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.fset

    def equal(self, other: "Function") -> bool:
        return super().equal(other)


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
        if self.module:
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
            if self._is_child_ignored(n, o):
                continue

            # break recursions
            if any(o is p for p in self.get_parents_obj_flat() + [self.python_obj]):
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
        pass

    @property
    def source(self) -> str:
        ret = inspect.getsource(self.python_obj)
        return ret

    def get_actions_for_update(self, new_obj: Object) -> List[BaseAction]:
        ret = []

        a = self.children
        b = new_obj.children
        new_objs_names = b.keys() - a.keys()
        new_objs = {n: b[n] for n in new_objs_names}
        for o in new_objs.values():
            ret.extend(
                o.get_actions_for_add(reloader=self.reloader, parent=self, obj=o)
            )

        deleted_objs_names = a.keys() - b.keys()
        deleted_objs = {n: a[n] for n in deleted_objs_names}
        for o in deleted_objs.values():
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

            ret.extend(o.get_actions_for_update(new_obj=b[n]))

        ret.sort(key=lambda a: a.priority, reverse=True)

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
            return f"Add: {repr(self.obj)}"

        def execute(self) -> None:
            self.pre_execute()
            source = dedent(self.obj.source)

            if isinstance(self.parent, Class):
                context = dict(self.parent.python_obj.__dict__)
                exec(source, self.parent.module.python_obj.__dict__, context)
                self.parent.set_attr(self.obj.name, context[self.obj.name])
            else:
                exec(source, self.parent.module.python_obj.__dict__)

    def __post_init__(self):
        super().__post_init__()

    def get_actions_for_update(self, new_obj: "Class") -> List["BaseAction"]:
        if [c.__name__ for c in self.python_obj.__mro__] == [c.__name__ for c in new_obj.python_obj.__mro__]:
            return super().get_actions_for_update(new_obj)
        else:
            raise FullReloadNeeded()

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        full_name = f"{self.full_name_without_module_name}.{name}"

        if full_name not in self.module.module_descriptor.source.flat_syntax:
            return True

        return False

    def get_dict(self) -> "OrderedDict[str, Any]":
        # members = inspect.getmembers(self.python_obj)
        # ret = OrderedDict(sorted(members))
        ret = OrderedDict(self.python_obj.__dict__)

        return ret

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        # If already process means it's just a reference
        if id(obj) in self.reloader.obj_to_modules and not self.is_primitive(obj):
            return {name: Reference}

        if isinstance(obj, classmethod):
            return {name: ClassMethod}

        if isinstance(obj, staticmethod):
            return {name: StaticMethod}

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
    ) -> List["BaseAction"]:
        ret = [self.Add(reloader=reloader, parent=parent, obj=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass
class Method(Function):
    @dataclass
    class Add(Function.Add):
        obj: "Method"
        parent: "Class"

        def execute(self) -> None:
            self.pre_execute()
            fun, code = self.obj.get_fixed_fun(self.obj, self.parent)
            self.obj.python_obj = fun
            self.obj.python_obj.__code__ = code
            setattr(self.parent.python_obj, self.obj.name, self.obj.python_obj)

    class Update(Function.Update):
        obj: "Method"
        new_obj: Optional["Method"]
        parent: "Class"

        def execute(self) -> None:
            self.pre_execute()
            self.old_code = self.obj.get_func(self.obj.python_obj).__code__

            fun, code = self.obj.get_fixed_fun(self.obj, self.parent)
            self.obj.get_func(self.obj.python_obj).__code__ = code

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj

    def get_fixed_fun(
        self, original_method: "Method", parent: Optional["ContainerObj"] = None
    ) -> Tuple[Callable, CodeType]:
        source = self.source
        source = re.sub(r"super\(\s*\)", f"super({self.parent.name}, self)", source)
        source = indent(source, "    " * 4)

        if not parent:
            parent = self.parent

        __class__str = f"__class__ = {parent.name}" if original_method.get_func(original_method.python_obj).__code__.co_freevars else ""
        builder = dedent(
            f"""
            def builder():
                {__class__str}\n{source}
                return {self.name}
            """
        )

        context = dict(parent.module.python_obj.__dict__)
        code = compile(builder, str(self.module.file), 'exec')
        exec(code, context)

        fixed_fun = context["builder"]()

        fixed_consts = []

        for c in self.get_func(fixed_fun).__code__.co_consts:
            if isinstance(c, str):
                fixed_consts.append(c.replace("builder.<locals>", self.parent.name))
            else:
                fixed_consts.append(c)

        fixed_consts = tuple(fixed_consts)

        code = CodeType(
            self.get_func(fixed_fun).__code__.co_argcount,  # integer
            self.get_func(fixed_fun).__code__.co_kwonlyargcount,  # integer
            self.get_func(fixed_fun).__code__.co_nlocals,  # integer
            self.get_func(fixed_fun).__code__.co_stacksize,  # integer
            original_method.get_func(original_method.python_obj).__code__.co_flags,  # integer
            self.get_func(fixed_fun).__code__.co_code,  # bytes
            fixed_consts,  # tuple
            self.get_func(fixed_fun).__code__.co_names,  # tuple
            self.get_func(fixed_fun).__code__.co_varnames,  # tuple
            original_method.get_func(original_method.python_obj).__code__.co_filename,  # string
            original_method.get_func(original_method.python_obj).__code__.co_name,  # string
            self.get_func(self.python_obj).__code__.co_firstlineno,  # integer
            self.get_func(self.python_obj).__code__.co_lnotab,  # bytes
            original_method.get_func(original_method.python_obj).__code__.co_freevars,  # tuple
            self.get_func(fixed_fun).__code__.co_cellvars,  # tuple
        )
        return fixed_fun, code

    def equal(self, other: "Function") -> bool:
        ret = self.source == other.source
        return ret

@dataclass
class ClassMethod(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.__func__

    def equal(self, other: "Function") -> bool:
        ret = self.source == other.source
        return ret


@dataclass
class StaticMethod(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.__func__

    def equal(self, other: "Function") -> bool:
        ret = self.source == other.source
        return ret


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
    def get_actions_for_update(self, new_obj: "All") -> List["BaseAction"]:
        if new_obj.python_obj == self.python_obj:
            return []
        ret = [self.Update(
            reloader=self.reloader,
            parent=self.parent,
            obj=self,
            new_obj=new_obj,
        )]
        ret.extend(self.get_star_import_updates_actions())
        return ret


@dataclass
class ClassVariable(Variable):
    def get_actions_for_update(self, new_obj: "Variable") -> List["BaseAction"]:
        if self.safe_compare(new_obj):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                obj=self,
                new_obj=new_obj,
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
    def get_actions_for_update(self, new_obj: "Variable") -> List["BaseAction"]:

        if self.safe_compare(new_obj):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                obj=self,
                new_obj=new_obj,
            )
        ]

        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass
class Import(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            self.pre_execute()
            module = sys.modules.get(self.obj.name, self.obj.python_obj)
            setattr(self.parent.python_obj, self.obj.name, module)

    def get_actions_for_update(self, new_obj: "Variable") -> List["BaseAction"]:
        return []

    # def get_actions_for_add(
    #     self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    # ) -> List["BaseAction"]:
    #     ret = [self.Add(reloader=reloader, parent=parent, obj=obj)]
    #     ret.extend(self.get_actions_for_dependent_modules())
    #     return ret

    def get_actions_for_delete(
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["BaseAction"]:
        return []


@dataclass
class Source:
    path: Path
    content: str = field(init=False)
    syntax: ast.AST = field(init=False)
    flat_syntax: Dict[str, ast.AST] = field(init=False)

    def __post_init__(self) -> None:
        self.content = self.path.read_text()
        self.syntax = ast.parse(self.content, str(self.path))
        self.flat_syntax = self._get_flat_syntax(self.syntax, parent="")
        pass

    def fetch_source(self):
        self.source = Source(self.path)

    def _get_flat_syntax(self, syntax: ast.AST, parent: str) -> Dict[str, ast.AST]:
        ret = {}

        for child in ast.iter_child_nodes(syntax):
            if hasattr(child, "name"):
                namespaced_name = child.name if not parent else f"{parent}.{child.name}"
                ret[namespaced_name] = type(child)
                ret.update(self._get_flat_syntax(child, namespaced_name))

            if hasattr(child, "body") and type(child) is not ast.FunctionDef:
                ret.update(self._get_flat_syntax(child, parent))

            if type(child) in [ast.Assign, ast.AnnAssign]:
                targets = child.targets if hasattr(child, "targets") else [child.target]

                for t in targets:
                    if type(t) is ast.Name:
                        namespaced_name = t.id if not parent else f"{parent}.{t.id}"
                        ret[namespaced_name] = type(child.value)
                    elif type(t) is ast.Attribute:
                        namespaced_name = f"{t.value}.{t.attr}" if not parent else f"{parent}.{t.value}.{t.attr}"
                        ret[namespaced_name] = type(child.value)

        return ret


@dataclass
class Module(ContainerObj):
    module_descriptor: "ModuleDescriptor"
    flat: Dict[str, Object] = field(init=False, default_factory=dict)
    python_obj_to_objs: Dict[int, List[Object]] = field(
        init=False, default_factory=lambda: defaultdict(list)
    )

    def __post_init__(self) -> None:
        self.python_obj = self.module_descriptor.module
        self.name = self.module_descriptor.name
        self.module = self
        self._collect_children()

    @property
    def file(self) -> Path:
        ret = self.module_descriptor.path
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
        return OrderedDict(self.python_obj.__dict__)

    @classmethod
    def _is_ignored(cls, name: str) -> bool:
        return False

    @property
    def final_objs(self) -> List[FinalObj]:
        """
        Return non container objs
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
        return f"Module: {self.module_descriptor.name}"

    def get_flat_repr(self) -> Dict[str, Object]:
        ret = {self.name: self}
        for o in self.children.values():
            ret.update(o.get_flat_repr())

        return ret


@dataclass
class UpdateModule(BaseAction):
    module_file: Path
    priority = 50
    module_descriptor: "ModuleDescriptor" = field(init=False)

    def __post_init__(self) -> None:
        self.module_descriptor = sys.modules.user_modules[str(self.module_file)][0]
        self.old_source = self.module_descriptor.source

    def execute(self) -> None:
        self.pre_execute()

        old_module = Module(module_descriptor=self.module_descriptor,
                            reloader=self.reloader, name=None,
                            python_obj=None,
                            parent=None,
                            module=None)

        trace = sys.gettrace()
        sys.settrace(None)
        module_obj = misc.import_from_file(old_module.file, self.reloader.root)
        sys.settrace(trace)

        module_descriptor = ModuleDescriptor(name=old_module.module_descriptor.name,
                                             path=old_module.module_descriptor.path,
                                             module=module_obj)
        new_module = Module(
            module_descriptor=module_descriptor,
            reloader=self.reloader,
            name=old_module.name,
            python_obj=None,
            parent=None,
            module=None)

        actions = old_module.get_actions_for_update(new_module)
        actions.sort(key=lambda a: a.priority, reverse=True)

        for a in actions:
            if isinstance(a, UpdateModule) and self.reloader.is_already_reloaded(a.module_descriptor):
                continue

            a.execute()

        self.module_descriptor.fetch_source()

    def rollback(self) -> None:
        self.module_descriptor.source = self.old_source

    def __repr__(self) -> str:
        return f"Update: Module: {self.module_descriptor.name}"


@dataclass
class Dependency:
    module_file: Path
    objs: Set[Tuple[str, int]]  # name, id


@dataclass
class ModuleDescriptor:
    name: str
    path: Path
    module: ModuleType
    source: Source = field(init=False)

    def __post_init__(self):
        self.fetch_source()

    def fetch_source(self) -> None:
        self.source = Source(self.path)

    def __hash__(self) -> int:
        return hash(self.name)

    def __repr__(self):
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
                              module=value)
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
            left = self.python_obj_to_dict(a.obj.python_obj)
            right = self.python_obj_to_dict(a.new_obj.python_obj)
            pass


@dataclass
class PartialReloader:
    root: Path
    logger: Logger
    named_obj_to_modules: DefaultDict[Tuple[str, int], Set[ModuleDescriptor]] = field(init=False,
                                                                                default_factory=lambda: defaultdict(set))
    obj_to_modules: DefaultDict[int, Set[ModuleDescriptor]] = field(init=False,
                                                              default_factory=lambda: defaultdict(set))
    applied_actions: List[BaseAction] = field(init=False, default_factory=list)
    modules: Modules = field(init=False)
    tricky_types: TrickyTypes = field(init=False)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.logger.debug(f"Creating partial reloader for {self.root}")

        self.modules = Modules(self, sys.modules)
        sys.modules = self.modules
        dependency_watcher.enable()
        # self.tricky_types = TrickyTypes(reloader=self)
        # self.tricky_types.start()

    def _reset(self) -> None:
        self.named_obj_to_modules = defaultdict(set)
        self.obj_to_modules = defaultdict(set)
        self.applied_actions = []

    def is_already_reloaded(self, module_descr: ModuleDescriptor) -> bool:
        module_update_actions = [
            a for a in self.applied_actions if isinstance(a, UpdateModule)
        ]
        for a in module_update_actions:
            if a.module_descriptor is module_descr:
                return True

    def _collect_dependencies(self, module: ModuleDescriptor) -> None:
        for n, o in module.module.__dict__.items():
            if n.startswith("__") and n.endswith("__"):
                continue
            self.named_obj_to_modules[(n, id(o))].add(module)
            self.obj_to_modules[id(o)].add(module)

    def _collect_all_dependencies(self) -> None:
        for p, module_descr in copy(self.modules.user_modules).items():
            if self.root not in Path(p).parents:
                continue
            for m in list(module_descr):
                self._collect_dependencies(m)

        import_order = dependency_watcher.import_order

        # remove owner modules (original definition place)
        for key, modules in self.named_obj_to_modules.copy().items():
            sorted_modules = sorted(
                list(modules),
                key=lambda m: import_order.index(str(m.path)) if str(m.path) in import_order else 0
            )
            if sorted_modules:
                sorted_modules.pop(0)
            self.named_obj_to_modules[key] = set(sorted_modules)

        pass

    def reload(self, module_file: Path) -> None:
        """
        :return: True if succeded False i unable to reload
        """
        self._reset()
        self._collect_all_dependencies()

        action = UpdateModule(reloader=self,
                               module_file=module_file)
        action.execute()

    def rollback(self) -> None:
        for a in reversed(self.applied_actions):
            a.rollback()
