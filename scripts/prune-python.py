#!/usr/bin/env python3
"""Remove obsolete uv-managed Python installations from one Ansible runtime."""

import argparse
import re
import shutil
import sys
from pathlib import Path

INSTALLATION = re.compile(r"(?:cpython|pypy)-\d+\.\d+(?:\.\d+)?(?:[a-z]\d+)?[-+].+")


def obsolete_installations(runtime_dir, running_executable):
    runtime_dir = Path(runtime_dir).resolve(strict=True)
    store = runtime_dir / "python"
    if store.is_symlink():
        raise ValueError("The managed Python directory must not be a symlink.")
    store = store.resolve(strict=True)
    active = (runtime_dir / "venv/bin/python").resolve(strict=True)
    if active != Path(running_executable).resolve(strict=True):
        raise ValueError("Run cleanup using this runtime's venv/bin/python.")
    if not active.is_relative_to(store):
        raise ValueError(
            "The active Python is not in this runtime's managed Python directory."
        )

    candidates = []
    for entry in sorted(store.iterdir()):
        if not INSTALLATION.fullmatch(entry.name):
            continue
        # Preserve both the active installation and aliases resolving to it.
        if active.is_relative_to(entry.resolve()):
            continue
        if entry.is_symlink():
            candidates.append(entry)
        elif entry.is_dir() and any((entry / "bin").glob("python*")):
            candidates.append(entry)
    return candidates


def prune(runtime_dir, running_executable, dry_run=False):
    candidates = obsolete_installations(runtime_dir, running_executable)
    for entry in candidates:
        if dry_run:
            print(f"Would remove {entry}")
        elif entry.is_symlink():
            entry.unlink()
            print(f"Removed alias {entry}")
        else:
            shutil.rmtree(entry)
            print(f"Removed {entry}")
    if not candidates:
        print("No obsolete managed Python installations found.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_dir", type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="List candidates without deleting files."
    )
    args = parser.parse_args()
    try:
        prune(
            args.runtime_dir,
            getattr(sys, "_base_executable", sys.executable),
            args.dry_run,
        )
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Python cleanup failed: {error}\n")


if __name__ == "__main__":
    main()
