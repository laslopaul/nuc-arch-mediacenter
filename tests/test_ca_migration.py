"""Regressions for removing file-backed Step CA trust anchors."""

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


class CAMigrationTests(unittest.TestCase):
    def certificate(self, directory, name):
        certificate = directory / f"{name}.crt"
        result = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:1024",
                "-nodes",
                "-subj",
                f"/CN={name}",
                "-days",
                "1",
                "-keyout",
                str(directory / f"{name}.key"),
                "-out",
                str(certificate),
            ],
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return certificate

    def test_file_backed_anchors_are_removed_by_fingerprint(self):
        executable = shutil.which("ansible-playbook")
        if executable is None:
            self.fail("ansible-playbook is required")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            root = self.certificate(directory, "retired")
            unrelated = self.certificate(directory, "unrelated")
            anchors = directory / "anchors"
            anchors.mkdir()
            matching = [anchors / "nuc-step-ca.crt", anchors / "nuc-server.lan_123.crt"]
            for anchor in matching:
                shutil.copyfile(root, anchor)
                anchor.chmod(0o444)
            other = anchors / "nuc-server.lan_unrelated.crt"
            shutil.copyfile(unrelated, other)
            retained = directory / "docker/step/data/certs/root_ca.crt"
            retained.parent.mkdir(parents=True)
            shutil.copyfile(root, retained)

            # The old trust API must not be used for these file-backed entries.
            tools = directory / "tools"
            tools.mkdir()
            trust = tools / "trust"
            trust.write_text("#!/bin/sh\necho 'read-only certificate' >&2\nexit 1\n")
            trust.chmod(0o755)
            tasks = yaml.safe_load(
                (ROOT / "roles/docker/tasks/migrations/step-ca.yml").read_text()
            )
            start = next(
                i
                for i, task in enumerate(tasks)
                if task["name"] == "Check for the retained CA certificate"
            )
            end = next(
                i
                for i, task in enumerate(tasks)
                if task["name"].startswith("Remove the obsolete CA CLI")
            )
            selected = yaml.safe_dump(tasks[start:end]).replace(
                "/etc/ca-certificates/trust-source/anchors", str(anchors)
            )
            play = [
                {
                    "hosts": "localhost",
                    "gather_facts": False,
                    "vars": {"docker_path": str(directory / "docker")},
                    "tasks": yaml.safe_load(selected),
                    "handlers": [
                        {
                            "name": "Update CA trust",
                            "ansible.builtin.debug": {"msg": "trust store rebuilt"},
                        }
                    ],
                }
            ]
            playbook = directory / "migration.yml"
            playbook.write_text(yaml.safe_dump(play))
            command = [
                executable,
                "-i",
                "localhost,",
                "-c",
                "local",
                str(playbook),
                "-e",
                json.dumps({"ansible_python_interpreter": sys.executable}),
            ]
            environment = dict(
                os.environ,
                PATH=str(tools) + os.pathsep + os.environ["PATH"],
                ANSIBLE_LOCAL_TEMP=str(directory / "local-tmp"),
                ANSIBLE_REMOTE_TEMP=str(directory / "remote-tmp"),
            )
            first = subprocess.run(
                command, env=environment, text=True, capture_output=True
            )
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertTrue(all(not anchor.exists() for anchor in matching))
            self.assertEqual(other.read_bytes(), unrelated.read_bytes())
            self.assertTrue(retained.is_file())
            self.assertIn("trust store rebuilt", first.stdout)
            second = subprocess.run(
                command, env=environment, text=True, capture_output=True
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertNotIn("trust store rebuilt", second.stdout)
