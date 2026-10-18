"""Run against a disposable Arch VM in an inventory's [local] group."""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("inventory", type=Path)
args = parser.parse_args()
executable = shutil.which("ansible-playbook")
if not executable:
    raise SystemExit("Activate the shared environment first.")


def apply(playbook, extra=None, unchanged=False):
    command = [
        executable,
        "-i",
        str(args.inventory.resolve()),
        str(ROOT / playbook),
        "-e",
        "@" + str(ROOT / "tests/arch-vm/vars.yml"),
    ]
    if extra:
        command += ["-e", json.dumps(extra)]
    result = subprocess.run(
        command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    print(result.stdout, flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)
    if unchanged and any(
        int(count) for count in re.findall(r"changed=(\d+)", result.stdout)
    ):
        raise SystemExit("Second reconciliation changed the VM.")


apply("tests/arch-vm/prepare.yml")
apply("tests/arch-vm/converge.yml", {"gui_components": ["alacritty"]})
apply("tests/arch-vm/converge.yml", {"gui_components": ["alacritty"]}, unchanged=True)
apply("tests/arch-vm/converge.yml")
apply("tests/arch-vm/converge.yml", unchanged=True)
apply("tests/arch-vm/verify.yml")
apply("purge.yml", {"purge_gui_targets": ["firefox"]})
# The explicit purge must be idempotent too.
apply("purge.yml", {"purge_gui_targets": ["firefox"]}, unchanged=True)
apply("tests/arch-vm/verify.yml", {"expect_profile": False})
