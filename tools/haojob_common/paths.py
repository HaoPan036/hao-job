"""One guard for local runtime material: no symlinks; inside Git, ignored and untracked."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


# macOS exposes its standard temporary directories through these aliases.
SYSTEM_ALIASES = {Path("/var"): Path("/private/var"), Path("/tmp"): Path("/private/tmp")}


class PathPolicyError(ValueError):
    """``reason`` is ``symlink``, ``outside_git`` or ``not_private``; tools map it to their own message."""

    def __init__(self, reason: str, path: Path):
        super().__init__(f"{reason}: {path}")
        self.reason = reason
        self.path = path


def reject_symlinks(path: Path) -> None:
    """Reject a symbolic link in any component, including ones that do not exist yet."""
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    for component in (candidate, *candidate.parents):
        if component.is_symlink():
            if sys.platform == "darwin" and SYSTEM_ALIASES.get(component) == component.resolve():
                continue
            raise PathPolicyError("symlink", component)


def _git(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguments], capture_output=True, text=True, check=False)


def require_private_path(path: Path, *, allow_outside_git: bool, repository: Path | None = None) -> Path:
    """Return the resolved path, or raise :class:`PathPolicyError`.

    Inside a Git work tree the path must be ignored and untracked. Outside Git
    it is accepted only when ``allow_outside_git`` is true. Parent directories
    need not exist: the nearest existing ancestor locates the work tree. With
    ``repository``, Git is queried in that work tree instead of discovering one.
    """
    reject_symlinks(path)
    resolved = Path(path).resolve()
    if repository is None:
        ancestor = resolved.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        found = _git("-C", str(ancestor), "rev-parse", "--show-toplevel")
        if found.returncode:
            if allow_outside_git:
                return resolved
            raise PathPolicyError("outside_git", resolved)
        root = Path(found.stdout.strip()).resolve()
    else:
        root = Path(repository).resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        raise PathPolicyError("not_private", resolved) from None
    ignored = _git("-C", str(root), "check-ignore", "-q", "--", relative)
    tracked = _git("-C", str(root), "ls-files", "--", relative)
    if ignored.returncode or tracked.returncode or tracked.stdout:
        raise PathPolicyError("not_private", resolved)
    return resolved
