from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, List

from smartreload import BaseConfig
from smartreload.plugins import smart_django

if TYPE_CHECKING:
    from smartreload.partialreloader import Action


class Config(BaseConfig):
    def plugins(self) -> List[ModuleType]:
        return [smart_django]
