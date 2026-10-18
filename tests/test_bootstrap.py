"""Check bootstrap's shared interpreter setup without downloading dependencies."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_TOOL = ROOT / "tests/fixtures/bootstrap_tool.py"


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tools = Path(directory.name) / "tools"
        self.tools.mkdir()
        self.runtime = Path(directory.name) / "runtime"
        self.store = self.runtime / "python"
        self.store.mkdir(parents=True)
        self.marker = self.store / "retained-interpreter"
        self.marker.touch()
        self.stale = self.runtime / "venv/bin/python3.13"
        self.stale.parent.mkdir(parents=True)
        self.stale.touch()

        # An isolated PATH makes the selected backend deterministic on any host.
        for name in ["dirname", "mkdir", "chmod"]:
            command = shutil.which(name)
            if command is None:
                self.fail(f"Required test command is unavailable: {name}")
            (self.tools / name).symlink_to(command)
        (self.tools / "python3").symlink_to(sys.executable)

    def bootstrap(self, backend="uv", launcher="working"):
        tool = self.tools / backend
        shutil.copyfile(FAKE_TOOL, tool)
        tool.chmod(0o755)
        return subprocess.run(
            ["/bin/bash", str(ROOT / "scripts/bootstrap.sh"), str(self.runtime)],
            env=dict(
                os.environ,
                PATH=str(self.tools),
                BOOTSTRAP_TEST_LAUNCHER=launcher,
            ),
            text=True,
            capture_output=True,
            umask=0o077,
        )

    def test_uv_runtime_uses_shared_python_with_readable_permissions(self):
        result = self.bootstrap()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.stale.exists())
        self.assertTrue(self.marker.is_file())
        python = (self.runtime / "venv/bin/python").resolve()
        self.assertEqual(python.parent, self.store.resolve())
        for path in [
            self.runtime,
            self.runtime / "venv/bin",
            self.runtime / "venv/bin/ansible-galaxy",
            self.store,
            python,
        ]:
            self.assertEqual(path.stat().st_mode & 0o005, 0o005, str(path))

    def test_missing_launcher_fails_bootstrap(self):
        result = self.bootstrap(launcher="missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Bootstrap failed:", result.stderr)
        self.assertNotIn("Environment ready:", result.stdout)

    def test_missing_shebang_interpreter_fails_bootstrap(self):
        result = self.bootstrap(launcher="broken")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Bootstrap failed:", result.stderr)
        self.assertNotIn("Environment ready:", result.stdout)

    def test_system_python_fallback_clears_obsolete_executables(self):
        result = self.bootstrap(backend="python3.15")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.stale.exists())
        self.assertTrue(self.marker.is_file())
        self.assertTrue((self.runtime / "venv/bin/python").is_file())
