#!/usr/bin/env python3
"""
Minimal uv/system-Python stand-in used by the bootstrap integration tests.
"""

import os
import shutil
import sys
from pathlib import Path


def write_executable(path, contents="#!/bin/sh\nexit 0\n"):
    path.write_text(contents)
    path.chmod(0o700)


def main():
    tool = Path(sys.argv[0]).name
    if tool == "uv" and sys.argv[1] == "pip":
        return

    venv = Path(sys.argv[-1])
    if tool == "uv":
        assert sys.argv[1:-1] == ["venv", "--python", "3.15", "--clear"]
        assert os.environ["UV_PYTHON_PREFERENCE"] == "only-managed"
        store = Path(os.environ["UV_PYTHON_INSTALL_DIR"])
        assert store == venv.parent / "python"
        store.mkdir(exist_ok=True)
        python = store / "python3.15"
        write_executable(python)
    else:
        assert tool == "python3.15"
        assert sys.argv[1:-1] == ["-m", "venv", "--clear"]
        python = None

    # Model --clear so tests catch stale files and accidental store deletion.
    if venv.exists():
        shutil.rmtree(venv)
    (venv / "bin").mkdir(parents=True)
    if python is None:
        write_executable(venv / "bin/python")
    else:
        (venv / "bin/python").symlink_to(python)
    write_executable(venv / "bin/ansible-galaxy")

    launcher = os.environ["BOOTSTRAP_TEST_LAUNCHER"]
    if launcher == "working":
        write_executable(venv / "bin/ansible-pull")
    elif launcher == "broken":
        write_executable(
            venv / "bin/ansible-pull", "#!/nonexistent-bootstrap-test-python\n"
        )
    else:
        assert launcher == "missing"


if __name__ == "__main__":
    main()
