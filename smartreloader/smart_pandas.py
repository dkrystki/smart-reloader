from copy import copy
from typing import Any, List

import pandas as pd

from smartreloader.objects import ContainerObj, UserObject, Object


class Dataframe(UserObject):
    namespace = "Pandas"

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: ContainerObj) -> bool:
        if type(obj) is pd.DataFrame:
            return True

        return False

    def compare(self, against: Object) -> bool:
        return self.python_obj.equals(against.python_obj)


class Series(UserObject):
    namespace = "Pandas"

    @classmethod
    def is_candidate(cls, name: str, obj: Any, potential_parent: ContainerObj) -> bool:
        if type(obj) is pd.Series:
            return True

        return False

    def compare(self, against: Object) -> bool:
        return self.python_obj.equals(against.python_obj)
