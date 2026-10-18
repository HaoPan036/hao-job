from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[3]
SKILL = PACKAGE / ".agents" / "skills" / "hao-job"
INSTALLER = PACKAGE / "tools" / "skill-install" / "install.py"


class InstallerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="skill-install-test-")
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)
        (self.home / ".claude").mkdir()

    def installer(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(INSTALLER), "--home", str(self.home), *args],
                              capture_output=True, text=True, check=False)

    def test_install_links_every_detected_agent(self) -> None:
        self.assertEqual(self.installer().returncode, 0)
        for skills_dir in (".agents/skills", ".claude/skills"):
            link = self.home / skills_dir / "hao-job"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), SKILL.resolve())
            self.assertTrue((link / "SKILL.md").is_file())

    def test_repeat_install_is_a_no_op(self) -> None:
        self.installer()
        result = self.installer()
        self.assertEqual(result.returncode, 0)
        self.assertIn("already linked", result.stdout)

    def test_dry_run_changes_nothing(self) -> None:
        self.assertEqual(self.installer("--dry-run").returncode, 0)
        self.assertFalse((self.home / ".agents").exists())
        self.assertFalse((self.home / ".claude" / "skills").exists())

    def test_skips_agents_that_are_not_installed(self) -> None:
        (self.home / ".claude").rmdir()
        self.installer()
        self.assertFalse((self.home / ".claude").exists())
        self.assertTrue((self.home / ".agents" / "skills" / "hao-job").is_symlink())

    def test_never_overwrites_existing_skill(self) -> None:
        existing = self.home / ".claude" / "skills" / "hao-job"
        existing.mkdir(parents=True)
        result = self.installer()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(existing.is_dir() and not existing.is_symlink())

    def test_uninstall_removes_only_own_links(self) -> None:
        self.installer()
        other = self.home / ".agents" / "skills" / "hao-job"
        other.unlink()
        other.mkdir()
        self.installer("--uninstall")
        self.assertFalse((self.home / ".claude" / "skills" / "hao-job").exists())
        self.assertTrue(other.is_dir())


if __name__ == "__main__":
    unittest.main()
