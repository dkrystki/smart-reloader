from copy import copy
from typing import Any, List

from dataclasses import dataclass, field
from django.db.models.query_utils import DeferredAttribute

from smartreloader.objects import ClassVariable, ContainerObj, Object


class DbField(ClassVariable):
    @dataclass
    class Add(ClassVariable.Add):
        def execute(self) -> None:
            self.parent.set_attr(self.obj.name, self.obj.python_obj)

        def rollback(self) -> None:
            super().rollback()
            self.parent.del_attr(self.obj.name)

    @dataclass
    class Update(ClassVariable.Update):
        rollback_obj: DeferredAttribute = field(init=False)

        def execute(self) -> None:
            self.rollback_obj = copy(self.obj.python_obj)

        def rollback(self) -> None:
            super().rollback()
            # self.obj.parent.set_attr(self.obj.name, self.obj.python_obj)

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: "ContainerObj") -> bool:
        if type(obj) is DeferredAttribute:
            return True

        return False

    @classmethod
    def get_rank(cls) -> int:
        return 1000

    def compare(self, against: "Object") -> bool:
        return False

