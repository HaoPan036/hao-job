#!/usr/bin/env python3
"""Link the haojob skill into each agent's user-level skill directory.

Every target is a symlink back to this repository, so `git pull` updates all
agents at once. Existing files that this installer did not create are never
overwritten or removed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

SKILL_NAME = "haojob"
SKILL_SOURCE = Path(__file__).resolve().parents[2] / ".agents" / "skills" / SKILL_NAME

# (label, directory that must exist for the agent to count as installed,
#  skill directory). None means the target is always installed.
TARGETS = [
    ("Agent Skills standard: Codex, Cursor, Gemini CLI, and others", None, ".agents/skills"),
    ("Claude Code", ".claude", ".claude/skills"),
]


def links(home: Path) -> list[tuple[str, Path]]:
    found = []
    for label, marker, skills_dir in TARGETS:
        if marker is None or (home / marker).is_dir():
            found.append((label, home / skills_dir / SKILL_NAME))
    return found


def points_here(link: Path) -> bool:
    return link.is_symlink() and link.resolve() == SKILL_SOURCE


def install(home: Path, dry_run: bool) -> int:
    failures = 0
    for label, link in links(home):
        if points_here(link):
            print(f"ok       {link}  ({label}, already linked)")
            continue
        if link.exists() or link.is_symlink():
            print(f"skipped  {link}  ({label}): something else is already there; remove it first")
            failures += 1
            continue
        if not dry_run:
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(SKILL_SOURCE, target_is_directory=True)
        print(f"linked   {link} -> {SKILL_SOURCE}  ({label})")
    print("\nRestart open agent sessions so they discover the skill.")
    return 1 if failures else 0


def uninstall(home: Path, dry_run: bool) -> int:
    for label, link in links(home):
        if points_here(link):
            if not dry_run:
                link.unlink()
            print(f"removed  {link}  ({label})")
        elif link.exists() or link.is_symlink():
            print(f"kept     {link}  ({label}): not created by this installer")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--uninstall", action="store_true", help="remove links created by this installer")
    parser.add_argument("--dry-run", action="store_true", help="show what would change without changing it")
    parser.add_argument("--home", default=str(Path.home()), help=argparse.SUPPRESS)
    args = parser.parse_args()
    home = Path(args.home).expanduser()
    if args.uninstall:
        return uninstall(home, args.dry_run)
    return install(home, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
