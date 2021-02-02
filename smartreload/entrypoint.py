import subprocess
import sys
from pathlib import Path
from textwrap import dedent
from threading import Thread
from time import sleep
from typing import List


class SmartReload:

    def __init__(self):
        self.seed_file = Path("__smartreload__.py")

    def create_seed(self, path: str, argv: List[str]) -> None:
        source = f"""
        import importlib
        import runpy
        import sys

        
        from smartreload.reloader import Reloader
        from smartreload.dependency_watcher import register_module
        Reloader(__file__).start()
        
        sys.argv = [{", ".join([f'"{a}"' for a in argv])}]
        
        loader = importlib.machinery.SourceFileLoader("__main__", "{path}")
        spec = importlib.util.spec_from_loader("__main__", loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules["carwash"] = module
        register_module(module)
        loader.exec_module(module)
        """
        self.seed_file.write_text(dedent(source))

    def get_path_from_module_path(self, module_name: str) -> str:
        module_path_component = module_name.replace(".", "/") + ".py"
        for p in sys.path:
            full_path = Path(p) / module_path_component
            if full_path.exists():
                return full_path

    def remove_seed(self) -> None:
        def target():
            sleep(0.5)
            self.seed_file.unlink()

        Thread(target=target).start()

    def main(self):
        argv = sys.argv[1:]
        joined_argv = " ".join(argv)

        entry_point_source: str

        if "-m" in joined_argv:
            module_name = argv[next(i for i, arg in enumerate(argv) if "-m" in arg) + 1]
            self.create_seed(self.get_path_from_module_path(module_name), argv=argv)
        else:
            entry_point_source_path = Path(argv[next(i for i, arg in enumerate(argv) if ".py" in arg)])
            self.create_seed(entry_point_source_path, argv=argv)

        self.remove_seed()
        subprocess.run(["python", str(self.seed_file.name)], close_fds=False)


def _main() -> None:
    SmartReload().main()


if __name__ == "__main__":
    _main()
