import subprocess
import sys


def _main():
    python_args = ["python"]
    if ".py" not in "".join(sys.argv[1:]):
        python_args.append("-m")

    argv = python_args + sys.argv[1:]
    subprocess.run(argv, close_fds=False)


if __name__ == "__main__":
    _main()
