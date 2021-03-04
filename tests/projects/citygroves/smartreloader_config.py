from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, List

from smartreloader import BaseConfig
from smartreloader.plugins import smart_django

if TYPE_CHECKING:
    from smartreloader.partialreloader import Action


class Config(BaseConfig):
    def plugins(self) -> List[ModuleType]:
        return [smart_django]
