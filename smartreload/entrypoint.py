import os
import subprocess
import sys

import signal

from pathlib import Path
from textwrap import dedent
from threading import Thread
from time import sleep
from typing import List, Optional
import uuid


class SmartReload:
    def __init__(self):
        self.seed_file = Path(f"__smartreload_{uuid.uuid4()}__.py")

    def create_seed(
        self, root: Path, entry_point_file: Path, argv: List[str], is_binary: bool
    ) -> None:

        if is_binary:
            set_module = f"""sys.modules["__smartreloader_entrypoint__"] = module"""
        else:
            set_module = f"""sys.modules["{entry_point_file.stem}"] = module"""

        source = f"""
        import importlib
        import sys
        from pathlib import Path
        
        from smartreload import dependency_watcher
        from smartreload.misc import import_from_file
        
        sys.argv = [{", ".join([f'"{a}"' for a in argv])}]
        
        config_file = Path("smartreloader_config.py")
        
        if config_file.exists():
            config = import_from_file(config_file, package_root=Path(".")).Config()
        else:
            from smartreload.config import BaseConfig
            config = BaseConfig()
        
        from smartreload.reloader import Reloader
        
        Reloader("{str(root)}", config).start()
        
        loader = dependency_watcher.MyLoader("__main__", "{str(entry_point_file)}")
        spec = importlib.util.spec_from_loader("__main__", loader)
        module = importlib.util.module_from_spec(spec)
        {set_module}
        loader.exec_module(module)
        """
        self.seed_file.write_text(dedent(source))

    def get_path_from_module_path(self, module_name: str) -> Optional[Path]:
        module_path_component = module_name.replace(".", "/") + ".py"
        for p in sys.path:
            full_path = Path(p) / module_path_component
            if full_path.exists():
                return full_path.absolute()

        return None

    def get_path_from_binary(self, binary_name: str) -> Optional[Path]:
        paths = os.environ["PATH"].split(":")
        for p in paths:
            full_path = Path(p) / binary_name
            if full_path.exists():
                return full_path.absolute()

        return None

    def remove_seed(self) -> None:
        def target():
            sleep(2.0)
            self.seed_file.unlink()

        Thread(target=target).start()

    def main(self):
        argv = sys.argv[1:]

        to_remove = ["python", "python3", "-m"]

        for r in to_remove:
            if r in argv:
                argv.remove(r)

        entry_point_file = self.get_path_from_binary(argv[0])

        if not entry_point_file:
            module_name = argv[0]
            entry_point_file = self.get_path_from_module_path(module_name)

        if not entry_point_file:
            entry_point_file = Path(argv[0])

        self.create_seed(
            root=Path(os.getcwd()),
            entry_point_file=entry_point_file,
            argv=argv,
            is_binary=True,
        )

        self.remove_seed()
        proc = subprocess.Popen(["python", str(self.seed_file.name)])

        def signal_handler(sig, frame):
            proc.send_signal(sig)

        signals_to_propagte = [signal.SIGHUP,
                                signal.SIGINT,
                                signal.SIGQUIT,
                                signal.SIGILL,
                                signal.SIGTRAP,
                                signal.SIGABRT,
                                signal.SIGBUS,
                                signal.SIGFPE,
                                signal.SIGUSR1,
                                signal.SIGSEGV,
                                signal.SIGUSR2,
                                signal.SIGPIPE,
                                signal.SIGALRM,
                                signal.SIGTERM]
        for s in signals_to_propagte:
            signal.signal(s, signal_handler)

        proc.communicate()


def _main() -> None:
    SmartReload().main()


if __name__ == "__main__":
    _main()
