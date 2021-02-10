from pathlib import Path
from typing import TYPE_CHECKING, List

from smartreload.partialreloader import FullReloadNeeded

if TYPE_CHECKING:
    from smartreload.partialreloader import Action


class BaseConfig:
    def on_start(self) -> None:
        pass

    def before_full_reload(self, file: Path, reason: Exception) -> None:
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
            "**/__smartreload__.py",
            "**/smartreload_config.py",
        ]

    @property
    def watched_paths(self) -> List[str]:
        return ["**/*.py"]
