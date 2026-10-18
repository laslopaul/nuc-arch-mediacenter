"""Exercise runtime cleanup against real directory and symlink fixtures."""

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prune_python", ROOT / "scripts/prune-python.py"
)
if SPEC is None or SPEC.loader is None:
    raise ImportError("Cannot load scripts/prune-python.py")
CLEANUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLEANUP)


class PrunePythonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "runtime"
        self.store = self.root / "python"
        self.active = self.install("cpython-3.15.0-linux-x86_64-gnu", "python3.15")
        self.old = self.install("cpython-3.13.16-linux-x86_64-gnu", "python3.13")
        self.active_alias = self.store / "cpython-3.15-linux-x86_64-gnu"
        self.active_alias.symlink_to(self.active)
        self.old_alias = self.store / "cpython-3.13-linux-x86_64-gnu"
        self.old_alias.symlink_to(self.old)
        (self.root / "venv/bin").mkdir(parents=True)
        self.executable = self.active / "bin/python3.15"
        (self.root / "venv/bin/python").symlink_to(self.executable)
        self.unrelated = self.store / "notes"
        self.unrelated.mkdir()
        self.lock = self.store / ".lock"
        self.lock.write_text("")

    def install(self, name, binary):
        installation = self.store / name
        (installation / "bin").mkdir(parents=True)
        (installation / "bin" / binary).write_text("fixture")
        return installation

    def test_removes_old_installation_and_alias_but_preserves_current(self):
        with redirect_stdout(io.StringIO()):
            CLEANUP.prune(self.root, self.executable)
        self.assertFalse(self.old.exists())
        self.assertFalse(self.old_alias.is_symlink())
        self.assertTrue(self.executable.is_file())
        self.assertTrue(self.active_alias.is_dir())
        self.assertTrue((self.root / "venv/bin/python").is_file())
        self.assertTrue(self.unrelated.is_dir())
        self.assertTrue(self.lock.is_file())
        with redirect_stdout(io.StringIO()) as output:
            CLEANUP.prune(self.root, self.executable)
        self.assertIn("No obsolete", output.getvalue())

    def test_dry_run_lists_old_installation_without_deleting_it(self):
        with redirect_stdout(io.StringIO()) as output:
            CLEANUP.prune(self.root, self.executable, dry_run=True)
        self.assertIn(f"Would remove {self.old.resolve()}", output.getvalue())
        self.assertTrue(self.old.is_dir())
        self.assertTrue(self.old_alias.is_symlink())
        self.assertTrue(self.executable.is_file())

    def test_symlink_targets_outside_store_are_not_deleted(self):
        external = Path(self.directory.name) / "external"
        external.mkdir()
        alias = self.store / "cpython-3.12-linux-x86_64-gnu"
        alias.symlink_to(external)
        broken = self.store / "cpython-3.11-linux-x86_64-gnu"
        broken.symlink_to(self.store / "missing")
        with redirect_stdout(io.StringIO()):
            CLEANUP.prune(self.root, self.executable)
        self.assertTrue(external.is_dir())
        self.assertFalse(alias.is_symlink())
        self.assertFalse(broken.is_symlink())

    def test_wrong_interpreter_refuses_cleanup_before_any_deletion(self):
        with self.assertRaisesRegex(ValueError, "Run cleanup using"):
            CLEANUP.prune(self.root, self.old / "bin/python3.13")
        self.assertTrue(self.old.is_dir())
        self.assertTrue(self.executable.is_file())

    def test_external_active_interpreter_refuses_cleanup(self):
        external = Path(self.directory.name) / "python3.15"
        external.write_text("fixture")
        launcher = self.root / "venv/bin/python"
        launcher.unlink()
        launcher.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "not in this runtime"):
            CLEANUP.prune(self.root, external)
        self.assertTrue(self.old.is_dir())

    def test_symlinked_store_refuses_cleanup(self):
        original_store = self.root / "original-python"
        self.store.rename(original_store)
        self.store.symlink_to(original_store)
        with self.assertRaisesRegex(ValueError, "must not be a symlink"):
            CLEANUP.prune(self.root, self.executable)
        self.assertTrue(self.old.is_dir())
