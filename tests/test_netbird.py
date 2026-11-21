"""Check that NetBird reconciliation preserves an existing installation."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class NetBirdTests(unittest.TestCase):
    def test_current_client_and_existing_unit_are_not_reinstalled(self):
        executable = shutil.which("ansible-playbook")
        if executable is None:
            self.fail("ansible-playbook is required")
        defaults = yaml.safe_load(
            (ROOT / "roles/base/defaults/main.yml").read_text()
        )
        tasks = yaml.safe_load(
            (ROOT / "roles/base/tasks/netbird/present.yml").read_text()
        )
        # Exercise installation logic without host-specific systemd calls.
        tasks = [
            task for task in tasks if "ansible.builtin.systemd" not in task
        ]
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            binary = directory / "netbird"
            binary.write_text(
                '#!/bin/sh\nif [ "$1" = version ]; then\n'
                f'  echo "{defaults["netbird_version"]}"\n'
                'else\n  echo "unexpected NetBird command" >&2\n'
                "  exit 99\nfi\n"
            )
            binary.chmod(0o755)
            unit = directory / "netbird.service"
            unit.write_text("existing customized service unit")
            serialized = yaml.safe_dump(tasks).replace(
                "/etc/systemd/system/netbird.service", str(unit)
            )
            playbook = directory / "netbird.yml"
            playbook.write_text(
                yaml.safe_dump(
                    [
                        {
                            "hosts": "localhost",
                            "gather_facts": False,
                            "vars": dict(
                                defaults,
                                ansible_architecture="x86_64",
                                netbird_binary_path=str(binary),
                                netbird_cache_dir=str(directory / "cache"),
                            ),
                            "tasks": yaml.safe_load(serialized),
                            "handlers": [
                                {
                                    "name": "Restart NetBird",
                                    "ansible.builtin.fail": {
                                        "msg": (
                                            "A current installation "
                                            "must not restart"
                                        )
                                    },
                                }
                            ],
                        }
                    ]
                )
            )
            result = subprocess.run(
                [
                    executable,
                    "-i",
                    "localhost,",
                    "-c",
                    "local",
                    str(playbook),
                    "-e",
                    json.dumps({"ansible_python_interpreter": sys.executable}),
                ],
                env=dict(
                    os.environ,
                    ANSIBLE_LOCAL_TEMP=str(directory / "local-tmp"),
                    ANSIBLE_REMOTE_TEMP=str(directory / "remote-tmp"),
                ),
                text=True,
                capture_output=True,
            )
            self.assertEqual(
                result.returncode, 0, result.stdout + result.stderr
            )
            self.assertIn("changed=0", result.stdout)
            self.assertFalse((directory / "cache").exists())
            self.assertEqual(
                unit.read_text(), "existing customized service unit"
            )
