from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, List

from smartreloader import objects

if TYPE_CHECKING:
    from smartreloader.partialreloader import Action


class BaseConfig:
    def on_start(self, argv: List[str]) -> None:
        pass

    def before_full_reload(self, file: Path) -> None:
        pass

    def before_reload(self, file: Path) -> None:
        pass

    def after_reload(self, file: Path, actions: List["Action"]) -> None:
        pass

    def before_rollback(self, file: Path, actions: List["Action"]) -> None:
        pass

    def after_rollback(self, file: Path, actions: List["Action"]) -> None:
        pass

    @property
    def ignored_paths(self) -> List[str]:
        return [
            "**/.*",
            "**/*~",
            "**/__pycache__",
            "**/__smartreloader_*.py",
            "**/smartreloader_config.py",
        ]

    @property
    def watched_paths(self) -> List[str]:
        return ["**/*.py"]

    def plugins(self) -> List[ModuleType]:
        return [objects]
