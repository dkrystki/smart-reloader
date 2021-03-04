import sys
from abc import ABC
from collections import defaultdict
from copy import copy

from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from types import ModuleType
from typing import (
    Any,
    DefaultDict,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type, )

from . import dependency_watcher, objects
from smartreloader.objects.base_objects import Object, BaseAction

from .config import BaseConfig


__all__ = ["PartialReloader"]

from smartreloader.objects.modules import ModuleDescriptor, Modules, UpdateModule
from .objects import Stack


@dataclass
class Dependency:
    module_file: Path
    objs: Set[Tuple[str, int]]  # name, id


@dataclass
class ObjectClassesManager:
    reloader: "PartialReloader"

    obj_classes: List[Type[Object]] = field(init=False)
    obj_class_to_children_classes: Dict[Type[Object], List[Type[Object]]] = field(init=False, default_factory=lambda: defaultdict(list))

    def __post_init__(self):
        self.refresh()

    def refresh(self) -> None:
        self._collect_object_classes()
        self._collect_object_classes_children()

    def _collect_object_classes(self) -> None:
        self.object_classes = []
        for p in self.reloader.plugins:
            self._collect_object_classes_from_context(p.__dict__)

    def _collect_object_classes_from_context(self, context: Dict[str, Any]) -> None:
        for c in context.values():
            if not isinstance(c, type):
                continue
            if not issubclass(c, Object):
                continue

            if ABC in c.__bases__:
                continue

            if "namespace" in context:
                c.namespace = context["namespace"]

            self.object_classes.append(c)

    def _collect_object_classes_children(self) -> None:
        self.obj_class_to_children_classes = defaultdict(list)
        for c1 in self.object_classes:
            for c2 in self.object_classes:
                if c2.get_parent_classes() and any(issubclass(c1, pc) for pc in c2.get_parent_classes()):
                    self.obj_class_to_children_classes[c1].append(c2)


@dataclass
class PartialReloader:
    root: Path
    logger: Logger
    named_obj_to_modules: DefaultDict[Tuple[str, int], Set[ModuleDescriptor]] = field(init=False,
                                                                                default_factory=lambda: defaultdict(set))
    obj_to_modules: DefaultDict[int, Set[ModuleDescriptor]] = field(init=False,
                                                              default_factory=lambda: defaultdict(set))

    config: Optional["BaseConfig"] = BaseConfig()
    applied_actions: List[BaseAction] = field(init=False, default_factory=list)
    modules: Modules = field(init=False)
    object_classes_manager: ObjectClassesManager = field(init=False)
    plugins: List[ModuleType] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.logger.debug(f"Creating partial reloader for {self.root}")

        self.object_classes_manager = ObjectClassesManager(self)

        dependency_watcher.post_module_exec_hook = self.post_module_exec_hook

        self.modules = Modules(self, sys.modules)
        sys.modules = self.modules
        dependency_watcher.enable()

        self.add_plugin(objects)

        for p in self.config.plugins():
            self.add_plugin(p)

    def add_plugin(self, plugin: ModuleType) -> None:
        self.plugins.append(plugin)
        self.object_classes_manager.refresh()

    def post_module_exec_hook(self, module: ModuleType):
        module_descriptors = self.modules.user_modules.get(module.__file__, [])
        for m in module_descriptors:
            m.post_execute()

    def reset(self) -> None:
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
        for n, o in module.body.__dict__.items():
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

    def reload(self, module_file: Path, dry_run=False) -> None:
        """
        :return: True if succeded False i unable to reload
        """
        self.reset()
        self._collect_all_dependencies()

        update_module = UpdateModule(reloader=self,
                                     module_file=module_file)
        update_module.pre_execute()
        update_module.execute(dry_run)

        stack = Stack(logger=self.logger, module_file=module_file, reloader=self)
        stack.update()

    def rollback(self) -> None:
        for a in reversed(self.applied_actions):
            a.rollback()
