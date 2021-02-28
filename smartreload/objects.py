import ctypes
import gc
import inspect
import re
import sys
from abc import ABC
from collections import OrderedDict
from copy import copy

from dataclasses import field
from textwrap import dedent, indent
from types import CodeType,FrameType, FunctionType
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type, TYPE_CHECKING,
)

from dataclasses import dataclass

from .base_objects import FinalObj, BaseAction, Object, ContainerObj
from .exceptions import FullReloadNeeded
from .modules import Module


if TYPE_CHECKING:
    from .partialreloader import PartialReloader


@dataclass(repr=False)
class Foreigner(FinalObj):
    def fix_reference(self, module: "Module") -> None:
        if self.is_primitive(self.python_obj):
            return
        ret = self.get_python_obj_from_module(self.python_obj, module)
        if not ret:
            return
        self.python_obj = ret

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = name not in potential_parent.module.module_descriptor.source.flat_syntax
        return ret

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Module]

    @classmethod
    def get_rank(cls) -> int:
        return int(1e4)


@dataclass(repr=False)
class Reference(FinalObj):
    def fix_reference(self, module: "Module") -> None:
        if self.is_primitive(self.python_obj):
            return
        ret = self.get_python_obj_from_module(self.python_obj, module)
        if not ret:
            return
        self.python_obj = ret

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = potential_parent.module.is_already_processed(obj) and not Object.is_primitive(obj)
        return ret

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [ContainerObj]

    @classmethod
    def get_rank(cls) -> int:
        return int(1e4)


@dataclass(repr=False)
class Function(FinalObj):
    @dataclass(repr=False)
    class Update(FinalObj.Update):
        obj: "Function"
        new_obj: Optional["Function"]
        old_code: CodeType = field(init=False)

        def execute(self) -> None:
            self.old_code = self.obj.get_func(
                self.obj.python_obj
            ).__code__

            self.obj.get_func(
                self.obj.python_obj
            ).__code__ = self.new_obj.get_func(self.new_obj.python_obj).__code__

        def rollback(self) -> None:
            super().rollback()
            self.obj.get_func(self.obj.python_obj).__code__ = self.old_code

    @dataclass(repr=False)
    class Move(FinalObj.Update):
        obj: "Function"
        new_obj: Optional["Function"]

        def execute(self) -> None:
            self.obj.update_first_line_number(self.new_obj.get_func(self.new_obj.python_obj).__code__.co_firstlineno)

        def rollback(self) -> None:
            super().rollback()

        def __repr__(self) -> str:
            return f"Move {repr(self.obj)}"

    @dataclass(repr=False)
    class DeepUpdate(FinalObj.DeepUpdate):
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

        def execute(self) -> None:
            self.replace_obj(self.obj.python_obj, self.new_obj.python_obj)
            if hasattr(self.obj.python_obj, "__func__"):
                self.replace_obj(self.obj.python_obj.__func__, self.new_obj.python_obj)


    @classmethod
    def get_rank(cls) -> int:
        return 20

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Module]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = inspect.isfunction(obj)
        return ret

    def get_actions_for_update(self, new_obj: "Function") -> List["BaseAction"]:
        wrapped = self.extract_wrapped(new_obj.get_func(new_obj.python_obj)) or self.extract_wrapped(self.get_func(self.python_obj))
        if type(self.python_obj) != type(new_obj.python_obj) or wrapped:
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
        elif self.get_func(self.python_obj).__code__.co_firstlineno != new_obj.get_func(new_obj.python_obj).__code__.co_firstlineno:
            return [self.Move(reloader=self.reloader,
                    parent=self.parent,
                    obj=self,
                    new_obj=new_obj)]
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

    def extract_wrapped(self, decorated: FunctionType):
        if not decorated.__closure__:
            return None
        closure = (c.cell_contents for c in decorated.__closure__)
        ret = next((c for c in closure if isinstance(c, FunctionType)), None)
        return ret

    @property
    def source(self) -> str:
        func = self.get_func(self.python_obj)
        if func.__closure__:
            target = self.extract_wrapped(func) or func
        else:
            target = func

        source_lines = self.module.module_descriptor.source.content.splitlines(keepends=True)
        lnum = target.__code__.co_firstlineno - 1

        ret = inspect.getblock(source_lines[lnum:])
        ret = "".join(ret)

        ret = dedent(ret)
        ret = ret.strip()
        return ret

    def is_global(self) -> bool:
        ret = self.parent == self.module
        return ret

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj

    def update_first_line_number(self, new_line_number: int) -> None:
        func = self.get_func(self.python_obj)

        args_order = [
            "co_argcount",
            "co_kwonlyargcount",
            "co_nlocals",
            "co_stacksize",
            "co_flags",
            "co_code",
            "co_consts",
            "co_names",
            "co_varnames",
            "co_filename",
            "co_name",
            "co_firstlineno",
            "co_lnotab",
            "co_freevars",
            "co_cellvars"]
        kwargs = {k: getattr(func.__code__, k) for k in args_order}
        kwargs["co_firstlineno"] = new_line_number

        code = CodeType(
            *kwargs.values()
        )

        func.__code__ = code


@dataclass(repr=False)
class PropertyGetter(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.fget

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return []


@dataclass(repr=False)
class PropertySetter(Function):
    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.fset

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return []


@dataclass(repr=False)
class Property(Function):
    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Class]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = isinstance(obj, property)
        return ret

    @classmethod
    def get_candidate_content(cls, name: str, obj: Any, potential_parent: "ContainerObj",
                         module: "Module", reloader: "PartialReloader") -> Dict[str, "Object"]:
        ret = {}

        if obj.fget:
            ret[name] = PropertyGetter(python_obj=obj, name=name, parent=potential_parent,
                             reloader=reloader, module=module)
        if obj.fset:
            setter_name = name + "__setter__"
            ret[setter_name] = PropertySetter(python_obj=obj, name=setter_name, parent=potential_parent,
            reloader = reloader, module = module)

        return ret


@dataclass(repr=False)
class Class(ContainerObj):
    @dataclass(repr=False)
    class Add(ContainerObj.Add):
        def __repr__(self) -> str:
            return f"Add {repr(self.obj)}"

        def execute(self, dry_run=False) -> None:
            source = dedent(self.obj.source)

            if isinstance(self.parent, Class):
                context = dict(self.parent.python_obj.__dict__)
                exec(source, self.parent.module.python_obj.__dict__, context)
                fixed_python_obj = context[self.obj.name]
                self.obj.python_obj = fixed_python_obj
                self.parent.set_attr(self.obj.name, fixed_python_obj)
            else:
                exec(source, self.parent.module.python_obj.__dict__)
                fixed_python_obj = self.parent.module.python_obj.__dict__[self.obj.name]
                self.obj.python_obj = fixed_python_obj

            self.parent.module.register_obj(self.obj)

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        if name == "__all__":
            return False

        full_name = self.get_full_name_for_child(name)

        if self.is_obj_foreign(full_name):
            return True

        return False

    @classmethod
    def get_rank(cls) -> int:
        return 30

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Class, Module]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = inspect.isclass(obj) and name == obj.__name__
        return ret

    def get_actions_for_update(self, new_obj: "Class") -> List["BaseAction"]:
        if [c.__name__ for c in self.python_obj.__mro__] == [c.__name__ for c in new_obj.python_obj.__mro__]:
            return super().get_actions_for_update(new_obj)
        else:
            raise FullReloadNeeded()

    def get_dict(self) -> "OrderedDict[str, Any]":
        ret = OrderedDict(self.python_obj.__dict__)

        return ret

    def _python_obj_to_obj_classes(
        self, name: str, obj: Any
    ) -> Dict[str, Type[Object]]:
        return {name: ClassVariable}

    def get_actions_for_add(
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["BaseAction"]:
        ret = [self.Add(reloader=reloader, parent=parent, obj=obj)]
        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass(repr=False)
class Method(Function):
    @dataclass(repr=False)
    class Add(Function.Add):
        obj: "Method"
        parent: "Class"

        def execute(self) -> None:
            fun, code = self.obj.get_fixed_fun(self.obj, self.parent)
            self.obj.python_obj = fun
            self.obj.python_obj.__code__ = code
            setattr(self.parent.python_obj, self.obj.name, self.obj.python_obj)

    class Update(Function.Update):
        obj: "Method"
        new_obj: Optional["Method"]
        parent: "Class"

        def execute(self) -> None:
            self.old_code = self.obj.get_func(self.obj.python_obj).__code__

            fun, code = self.new_obj.get_fixed_fun(self.obj, self.parent)
            self.obj.get_func(self.obj.python_obj).__code__ = code

    @classmethod
    def get_rank(cls) -> int:
        return 10

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Class]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        return inspect.isfunction(obj)

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


@dataclass(repr=False)
class ClassMethod(Function):
    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Class]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = isinstance(obj, classmethod)
        return ret

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.__func__

    @classmethod
    def get_rank(cls) -> int:
        return 10

    def equal(self, other: "Function") -> bool:
        ret = self.source == other.source
        return ret


@dataclass(repr=False)
class StaticMethod(Function):
    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Class]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = isinstance(obj, staticmethod)
        return ret

    @classmethod
    def get_func(cls, obj: Any) -> Any:
        return obj.__func__

    @classmethod
    def get_rank(cls) -> int:
        return 10

    def equal(self, other: "Function") -> bool:
        ret = self.source == other.source
        return ret


@dataclass(repr=False)
class Dictionary(ContainerObj):
    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [ContainerObj]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = isinstance(obj, dict)
        return ret

    @classmethod
    def get_rank(cls) -> int:
        return 30

    def get_dict(self) -> "OrderedDict[str, Any]":
        return self.python_obj

    def set_attr(self, name: str, obj: "Any") -> None:
        self.python_obj[name] = obj

    def del_attr(self, name: str) -> None:
        del self.python_obj[name]


@dataclass(repr=False)
class Variable(FinalObj):
    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Module, ListObj, TupleObj]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        if name.startswith("__") and name.endswith("__"):
            return False

        return True

    @classmethod
    def get_rank(cls) -> int:
        return 5


@dataclass(repr=False)
class All(FinalObj):
    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Module]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = name == "__all__"
        return ret

    @classmethod
    def get_rank(cls) -> int:
        return 80

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


@dataclass(repr=False)
class ClassVariable(Variable):
    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Class]

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        if name.startswith("__") and name.endswith("__"):
            return False

        if name in [
            "_abc_generic_negative_cache",
            "_abc_registry",
            "_abc_cache",
        ]:
            return False

        return True

    @classmethod
    def get_rank(cls) -> int:
        return 5


@dataclass(repr=False)
class DictionaryItem(FinalObj):
    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        return True

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Dictionary]

    def get_actions_for_update(self, new_obj: "Variable") -> List["BaseAction"]:
        ret = []
        ret.extend(self.get_update_actions_for_not_equal(new_obj))

        if not ret:
            return ret

        ret.extend(self.get_actions_for_dependent_modules())
        return ret


@dataclass(repr=False)
class Import(FinalObj):
    class Add(FinalObj.Add):
        def execute(self) -> None:
            module = sys.modules.get(self.obj.name, self.obj.python_obj)
            setattr(self.parent.python_obj, self.obj.name, module)

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = inspect.ismodule(obj)
        return ret

    @classmethod
    def get_rank(cls) -> int:
        return 30

    def get_actions_for_update(self, new_obj: "Variable") -> List["BaseAction"]:
        return []

    # def get_actions_for_add(
    #     self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    # ) -> List["BaseAction"]:
    #     ret = [self.Add(reloader=reloader, parent=parent, obj=obj)]
    #     ret.extend(self.get_actions_for_dependent_modules())
    #     return ret

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [Module]

    def get_actions_for_delete(
        self, reloader: "PartialReloader", parent: "ContainerObj", obj: "Object"
    ) -> List["BaseAction"]:
        return []

    @classmethod
    def get_rank(cls) -> int:
        return int(2e4)


@dataclass(repr=False)
class UserObject(Object, ABC):
    @classmethod
    def get_rank(cls) -> int:
        return 100


@dataclass(repr=False)
class Iterable(ContainerObj, ABC):
    class Update(ContainerObj.Update):
        obj: "ListObj"
        new_obj: Optional["ListObj"]
        parent: "ContainerObj"

        def execute(self) -> None:
            self.obj.python_obj.clear()
            self.new_obj.fix_reference(self.obj.module)
            self.obj.python_obj.extend(self.new_obj.python_obj)

    def collect_children(self) -> None:
        for i, o in enumerate(self.python_obj):
            name = str(i)
            won_candidate = self._get_winning_candidate(name=name, obj=o)
            if won_candidate:
                self._add_candidate(won_candidate)

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [ContainerObj]


@dataclass(repr=False)
class ListObj(Iterable):
    python_obj: list

    def fix_reference(self, module: "Module") -> Any:
        self.python_obj.clear()
        ret = []
        for o in self.children.values():
            o.fix_reference(module)
            ret.append(o.python_obj)

        self.python_obj.extend(ret)

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = isinstance(obj, list)
        return ret

    def get_actions_for_update(self, new_obj: "Variable") -> List["BaseAction"]:
        ret = []
        ret.extend(self.get_update_actions_for_not_equal(new_obj))

        if not ret:
            return ret

        ret.extend(self.get_actions_for_dependent_modules())
        return ret

    @classmethod
    def get_obj_type_name(cls) -> str:
        return "List"


@dataclass(repr=False)
class TupleObj(Iterable):
    python_obj: tuple

    class DeepUpdate(Iterable.DeepUpdate):
        obj: "Tuple"
        new_obj: Optional["Tuple"]

    def fix_reference(self, module: "Module") -> Any:
        ret = []
        for o in self.children.values():
            o.fix_reference(module)
            ret.append(o.python_obj)

        self.python_obj = tuple(ret)

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        ret = isinstance(obj, tuple)
        return ret

    def get_actions_for_update(self, new_obj: "Variable") -> List["BaseAction"]:
        ret = [
                self.DeepUpdate(
                    reloader=self.reloader,
                    parent=self.parent,
                    obj=self,
                    new_obj=new_obj,
                )
            ]

        return ret

    @classmethod
    def get_obj_type_name(cls) -> str:
        return "Tuple"
