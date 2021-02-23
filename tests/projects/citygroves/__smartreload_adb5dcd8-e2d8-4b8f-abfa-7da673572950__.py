
import importlib
import sys
from pathlib import Path

from smartreload import dependency_watcher
from smartreload.misc import import_from_file

sys.argv = ["./manage.py", "runserver", "--noreload"]

config_file = Path("smartreloader_config.py")

if config_file.exists():
    config = import_from_file(config_file, package_root=Path(".")).Config()
else:
    from smartreload.config import BaseConfig
    config = BaseConfig()

from smartreload.reloader import Reloader

Reloader("/home/kwazar/Code/opensource/smartreload/tests/projects/citygroves", config).start()

loader = dependency_watcher.MyLoader("__main__", "manage.py")
spec = importlib.util.spec_from_loader("__main__", loader)
module = importlib.util.module_from_spec(spec)
sys.modules["__smartreloader_entrypoint__"] = module
loader.exec_module(module)
