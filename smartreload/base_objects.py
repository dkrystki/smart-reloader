import ctypes
import inspect
import gc
from abc import ABC
from collections import OrderedDict
from copy import copy
from pathlib import Path
from types import FrameType

from dataclasses import field
from textwrap import dedent
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    Type, TYPE_CHECKING,
)

from . import dependency_watcher


from dataclasses import dataclass


if TYPE_CHECKING:
    from . import PartialReloader
    from .modules import Module


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

    def post_execute(self):
        pass

    def pre_execute(self) -> None:
        self.reloader.applied_actions.append(self)
        self.log()


@dataclass
class Action(BaseAction):
    obj: "Object"


@dataclass(repr=False)
class Object(ABC):
    @dataclass(repr=False)
    class Add(Action):
        parent: "ContainerObj"
        obj: "Object"

        def __repr__(self) -> str:
            return f"Add {repr(self.obj)}"

        def execute(self) -> None:
            self.obj.fix_reference(self.parent.module)
            self.parent.set_attr(self.obj.name, self.obj.python_obj)

        def post_execute(self):
            self.parent.module.register_obj(self.obj)

        def rollback(self) -> None:
            super().rollback()
            self.parent.del_attr(self.obj.name)
            self.parent.module.unregister_obj(self.obj)

    @dataclass(repr=False)
    class Update(Action):
        parent: Optional["ContainerObj"]
        obj: "Object"
        new_obj: Optional["Object"]

        def __repr__(self) -> str:
            return f"Update {repr(self.obj)}"

        def execute(self) -> None:
            self.new_obj.fix_reference(self.obj.module)
            self.obj.parent.set_attr(self.obj.name, self.new_obj.python_obj)

        def rollback(self) -> None:
            super().rollback()
            self.obj.parent.set_attr(self.obj.name, self.obj.python_obj)

    @dataclass(repr=False)
    class DeepUpdate(Action):
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
            owner: "Object.DeepUpdate"

            def execute(self) -> None:
                self.dictionary[self.key] = self.value
                if inspect.isframe(self.dict_obj):
                    self.owner.apply_changes_to_frame(self.dict_obj)

        rollback_operations: List[RollabackOperation] = field(init=False, default_factory=list)

        def __post_init__(self):
            pass

        def get_referrers(self, obj: object) -> List[object]:
            ret = []
            referres = gc.get_referrers(obj)
            for r in referres:
                if r is locals():
                    continue

                # exclude frames coming from this library
                if inspect.isframe(r) and Path(__file__).parent in Path(r.f_code.co_filename).parents:
                    continue

                ret.append(r)
            return ret

        def __repr__(self) -> str:
            return f"DeepUpdate {repr(self.obj)}"

        def replace_obj(self, what: object, to_what: object):
            referrers = self.get_referrers(what)

            for r in referrers:
                if r is locals():
                    continue

                if isinstance(r, dict):
                    dictionary = r

                elif inspect.isframe(r):
                    dictionary = r.f_locals
                else:
                    continue

                for k, v in dictionary.items():
                    if v is not what:
                        continue
                    dictionary[k] = to_what
                    self.rollback_operations.append(self.RollabackOperation(r, dictionary, k, v, self))

                # update frame
                if inspect.isframe(r):
                    self.apply_changes_to_frame(r)

        def execute(self) -> None:
            self.replace_obj(self.obj.python_obj, self.new_obj.python_obj)

        def rollback(self) -> None:
            super().rollback()

            for o in self.rollback_operations:
                o.execute()

        def apply_changes_to_frame(self, frame_obj: FrameType):
            if inspect.isframe(frame_obj):
                ctypes.pythonapi.PyFrame_LocalsToFast(
                    ctypes.py_object(frame_obj),
                    ctypes.c_int(1))

    @dataclass(repr=False)
    class Delete(Action):
        parent: Optional["ContainerObj"]
        obj: "Object"

        def __repr__(self) -> str:
            return f"Delete {repr(self.obj)}"

        def execute(self) -> None:
            self.parent.del_attr(self.obj.name)

        def rollback(self) -> None:
            super().rollback()
            self.parent.set_attr(self.obj.name, self.obj.python_obj)

    @dataclass(repr=False)
    class Candidate:
        rank: int
        content: Dict[str, "Object"]

        def __repr__(self) -> str:
            return repr(self.content)

    python_obj: Any
    name: Optional[str]
    parent: Optional["ContainerObj"]
    module: Optional["Module"]
    reloader: "PartialReloader"

    namespace: ClassVar[str] = ""

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        raise NotImplementedError()

    @classmethod
    def get_candidate_content(cls, name: str, obj: Any, potential_parent: "ContainerObj",
                         module: "Module", reloader: "PartialReloader") -> Dict[str, "Object"]:
        ret = {name: cls(python_obj=obj, name=name, parent=potential_parent,
                                         reloader=reloader, module=module)}
        return ret

    @classmethod
    def get_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj",
                      module: "Module", reloader: "PartialReloader") -> Optional["Object.Candidate"]:
        if cls.is_candidate(name=name, obj=obj, potential_parent=potential_parent):
            return cls.Candidate(rank=cls.get_rank(),
                            content=cls.get_candidate_content(name, obj, potential_parent, module, reloader))

        else:
            return None

    @classmethod
    def get_rank(cls) -> int:
        return 1

    @property
    def bare_name(self) -> str:
        ret = self.full_name.split(".")[-1]
        return ret

    @classmethod
    def get_parent_classes(cls) -> List[Type["ContainerObj"]]:
        return [ContainerObj]

    def compare(self, against: "Object") -> bool:
        try:
            return self.python_obj.__dict__ == against.python_obj.__dict__
        except AttributeError:
            pass
        try:
            ret = bool(self.python_obj == against.python_obj)
        except Exception as e:
            return False

        return ret

    def get_update_actions_for_not_equal(self, new_obj: "Object") -> List["BaseAction"]:
        if self.compare(new_obj):
            return []

        ret = [
            self.Update(
                reloader=self.reloader,
                parent=self.parent,
                obj=self,
                new_obj=new_obj,
            )
        ]

        return ret

    def get_actions_for_update(self, new_obj: "Object") -> List["BaseAction"]:
        ret = []
        ret.extend(self.get_update_actions_for_not_equal(new_obj))

        if not ret:
            return ret

        ret.extend(self.get_actions_for_dependent_modules())
        return ret

    def is_obj_foreign(self, obj_full_name: str) -> bool:
        ret = obj_full_name not in self.module.module_descriptor.source.flat_syntax
        return ret

    def fix_reference(self, module: "Module") -> Any:
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
        # while not root
        while obj.parent is not self.parent:
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
            from smartreload.modules import UpdateModule
            ret.append(UpdateModule(reloader=self.reloader, module_file=m_descr.path))

        return ret

    @staticmethod
    def is_primitive(obj: Any) -> bool:
        if obj is None:
            return True

        ret = any(
            type(obj) is p or obj is p
            for p in [str, bool, int, float]
        )
        return ret

    def equal(self, other: "Object") -> bool:
        return self.python_obj == other.python_obj

    def not_equal(self, other: "Object") -> bool:
        return self.python_obj != other.python_obj

    @classmethod
    def get_obj_type_name(cls) -> str:
        return cls.__name__

    def __repr__(self) -> str:
        namespace = self.namespace + "." if self.namespace else ""
        return f"{namespace}{self.get_obj_type_name()}: {self.full_name}"

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
                from smartreload.modules import UpdateModule
                ret.append(UpdateModule(reloader=self.reloader, module_file=m.path))

        return ret


@dataclass(repr=False)
class FinalObj(Object, ABC):
    def fix_reference(self, module: "Module") -> Any:
        if self.is_obj_foreign(self.full_name_without_module_name) or self.is_primitive(
            self.python_obj
        ):
            return
        fixed_reference_obj = self.get_python_obj_from_module(
            self.python_obj, module
        )
        try:
            self.python_obj.__class__ = fixed_reference_obj.__class__
        except TypeError:
            pass


@dataclass(repr=False)
class ContainerObj(Object, ABC):
    children: Dict[str, "Object"] = field(init=False, default_factory=dict)

    def get_dict(self) -> "OrderedDict[str, Any]":
        raise NotImplementedError()

    def _is_child_ignored(self, name: str, obj: Any) -> bool:
        return False

    @property
    def child_classes(self) -> List[Type[Object]]:
        ret = self.reloader.object_classes_manager.obj_class_to_children_classes[self.__class__]
        return ret

    def _get_winning_candidate(self, name: str, obj: Any) -> Optional[Object.Candidate]:
        all_candidates = []
        for c in self.child_classes:
            candidate = c.get_candidate(name, obj, potential_parent=self, module=self.module,
                                         reloader=self.reloader)
            if not candidate:
                continue
            all_candidates.append(candidate)

        candidates = sorted(all_candidates, key=lambda x: x.rank)
        if candidates:
            return candidates[-1]

        return None

    def _add_candidate(self, candidate: Object.Candidate) -> None:
        self.children.update(candidate.content)

        for o in candidate.content.values():
            self.module.register_obj(o)
            if isinstance(o, ContainerObj):
                o.collect_children()

    def collect_children(self) -> None:
        for n, o in self.get_dict().items():
            if self._is_child_ignored(n, o):
                continue

            # break recursions
            if any(o is p for p in self.get_parents_obj_flat() + [self.python_obj]):
                continue

            won_candidate = self._get_winning_candidate(name=n, obj=o)

            if won_candidate:
                self._add_candidate(won_candidate)

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

    def get_full_name_for_child(self, name: str) -> str:
        ret = f"{self.full_name_without_module_name}.{name}" if self.full_name_without_module_name else name
        return ret

    @classmethod
    def get_rank(cls) -> int:
        return 50

