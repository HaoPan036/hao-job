"""Runtime path guard; temporary repositories only."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLS))
from haojob_common import PathPolicyError, reject_symlinks, require_private_path


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, TOOLS / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(shutil.which("git"), "Git is required")
class PathGuardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.repo = self.base / "repo"
        subprocess.run(["git", "init", "--quiet", str(self.repo)], check=True)
        (self.repo / ".gitignore").write_text("private/\n")
        (self.repo / "private").mkdir()
        self.outside = self.base / "outside"
        self.outside.mkdir()

    def reason(self, path, **options):
        with self.assertRaises(PathPolicyError) as caught:
            require_private_path(path, **options)
        return caught.exception.reason

    def test_ignored_untracked_paths_pass_even_before_parents_exist(self):
        for allow in (True, False):
            with self.subTest(allow_outside_git=allow):
                target = self.repo / "private/new/deeper/file.json"
                self.assertEqual(require_private_path(target, allow_outside_git=allow), target)
                self.assertFalse((self.repo / "private/new").exists())

    def test_tracked_or_unignored_paths_fail_inside_git(self):
        public = self.repo / "public.json"
        public.write_text("{}")
        self.assertEqual(self.reason(public, allow_outside_git=True), "not_private")
        self.assertEqual(self.reason(self.repo / "missing/dir/file.json", allow_outside_git=True), "not_private")
        tracked = self.repo / "private/tracked.json"
        tracked.write_text("{}")
        subprocess.run(["git", "-C", str(self.repo), "add", "-f", str(tracked)], check=True)
        self.assertEqual(self.reason(tracked, allow_outside_git=True), "not_private")
        self.assertEqual(self.reason(self.repo / "private", allow_outside_git=True), "not_private")

    def test_outside_git_depends_on_explicit_policy(self):
        target = self.outside / "new/file.json"
        self.assertEqual(require_private_path(target, allow_outside_git=True), target)
        self.assertEqual(self.reason(target, allow_outside_git=False), "outside_git")

    def test_symlink_in_any_component_is_rejected(self):
        real = self.repo / "private/real"
        real.mkdir()
        (self.repo / "private/link").symlink_to(real, target_is_directory=True)
        (self.repo / "private/file-link.json").symlink_to(real / "file.json")
        (self.repo / "private/broken").symlink_to(self.base / "absent")
        for path in (self.repo / "private/link/new/file.json", self.repo / "private/file-link.json", self.repo / "private/broken"):
            for allow in (True, False):
                with self.subTest(path=path, allow_outside_git=allow):
                    self.assertEqual(self.reason(path, allow_outside_git=allow), "symlink")
            with self.assertRaises(PathPolicyError):
                reject_symlinks(path)
        reject_symlinks(self.repo / "private/real/file.json")

    def test_explicit_repository_is_used_for_git_queries(self):
        nested = self.repo / "private/nested"
        subprocess.run(["git", "init", "--quiet", str(nested)], check=True)
        target = nested / "file.json"
        self.assertEqual(require_private_path(target, allow_outside_git=False, repository=self.repo), target)
        self.assertEqual(self.reason(target, allow_outside_git=False), "not_private")
        self.assertEqual(self.reason(self.outside / "file.json", allow_outside_git=False, repository=self.repo), "not_private")


@unittest.skipUnless(shutil.which("git"), "Git is required")
class ToolPolicyTests(unittest.TestCase):
    """Each tool keeps its own inside/outside-Git policy; symlinks are rejected by all."""

    @classmethod
    def setUpClass(cls):
        cls.radar = load("common_paths_radar", "job-radar/radar.py")
        sys.path.insert(0, str(TOOLS / "job-radar"))
        import changedetection_bridge
        import collect
        import install_changedetection
        cls.collect, cls.bridge, cls.installer = collect, changedetection_bridge, install_changedetection
        cls.sync = load("common_paths_sync", "recruiting-sync/sync.py")

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.outside = self.base / "outside/file.md"
        self.outside.parent.mkdir()
        self.outside.write_text("fictional\n")
        self.link = self.base / "link.md"
        self.link.symlink_to(self.outside)

    def test_discovery_tools_accept_outside_git_but_reject_symlinks(self):
        for check in (self.radar.require_local_runtime_path, self.collect.require_runtime_path):
            with self.subTest(check=check.__qualname__):
                check(self.outside)
                with self.assertRaisesRegex(ValueError, "symbolic links"):
                    check(self.link)

    def test_record_tools_still_require_git(self):
        with self.assertRaisesRegex(self.bridge.BridgeError, "Git repository"):
            self.bridge.private_path(self.outside)
        with self.assertRaises(self.bridge.BridgeError):
            self.bridge.private_path(self.link)
        with self.assertRaisesRegex(ValueError, "inside Git"):
            self.installer.require_ignored_path(self.outside)
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            self.installer.require_ignored_path(self.link)
        with self.assertRaisesRegex(self.sync.SyncError, "repository root required"):
            self.sync.repository(self.outside.parent)


if __name__ == "__main__":
    unittest.main()
