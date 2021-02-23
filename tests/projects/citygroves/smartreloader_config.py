from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, List

from smartreload import BaseConfig, smart_django
from smartreload.partialreloader import FullReloadNeeded

if TYPE_CHECKING:
    from smartreload.partialreloader import Action


class Config(BaseConfig):
    def plugins(self) -> List[ModuleType]:
        return [smart_django]
