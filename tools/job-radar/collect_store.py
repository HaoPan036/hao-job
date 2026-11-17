"""Local collector state: runtime path checks, atomic writes, SQLite seen store and source health."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
from dataclasses import replace
from pathlib import Path

import radar
from haojob_common import paths as common_paths
from collect_base import ScoredItem, parse_iso_date

load_json = radar.load_json


def load_source_health(path: Path) -> dict:
    if not path.exists():
        return {
            "updated_at": None,
            "sources": {},
            "bridge": {"consecutive_failures": 0},
        }
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("source health must be an object")
    if not isinstance(payload.get("sources"), dict):
        payload["sources"] = {}
    if not isinstance(payload.get("bridge"), dict):
        payload["bridge"] = {"consecutive_failures": 0}
    return payload


def save_source_health(path: Path, state: dict) -> None:
    atomic_write(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def update_source_health(
    path: Path,
    sources: list[dict],
    errors: list[str],
    now: dt.datetime | None = None,
) -> dict:
    observed_at = now or dt.datetime.now().astimezone()
    observed_date = observed_at.date()
    state = load_source_health(path)
    source_state = dict(state["sources"])
    active_sources = [
        source
        for source in sources
        if source.get("enabled", True) and source.get("type", "html") != "manual"
    ]
    failed_names = {
        str(source["name"])
        for source in active_sources
        if any(error.startswith(f"{source['name']}:") for error in errors)
    }
    for source in active_sources:
        name = str(source["name"])
        record = dict(source_state.get(name) or {})
        record.setdefault("last_success_at", None)
        if name in failed_names:
            last_failure_date = record.get("last_failure_date")
            if last_failure_date == observed_date.isoformat():
                failures = max(1, int(record.get("consecutive_failures") or 0))
            elif last_failure_date == (observed_date - dt.timedelta(days=1)).isoformat():
                failures = int(record.get("consecutive_failures") or 0) + 1
            else:
                failures = 1
            record.update(
                {
                    "consecutive_failures": failures,
                    "last_failure_at": observed_at.isoformat(),
                    "last_failure_date": observed_date.isoformat(),
                }
            )
        else:
            record.update(
                {
                    "consecutive_failures": 0,
                    "last_success_at": observed_at.isoformat(),
                }
            )
        source_state[name] = record
    state.update(
        {
            "updated_at": observed_at.isoformat(),
            "sources": source_state,
        }
    )
    save_source_health(path, state)
    return state


def init_db(path: Path) -> sqlite3.Connection:
    reject_symlinks(path)
    for suffix in ("-wal", "-shm", "-journal"):
        reject_symlinks(path.with_name(path.name + suffix))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                score INTEGER NOT NULL
            )
            """
        )
        conn.commit()
    except Exception:
        conn.close()
        raise
    return conn


def mark_seen(conn: sqlite3.Connection, scored: ScoredItem, now: str) -> ScoredItem:
    row = conn.execute(
        "SELECT key, first_seen FROM seen_jobs WHERE key = ?", (scored.key,)
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT key, first_seen FROM seen_jobs WHERE url = ? LIMIT 1",
            (scored.item.url,),
        ).fetchone()
    first_observation = row is None
    is_new = first_observation or local_calendar_date(row[1]) == local_calendar_date(now)
    if first_observation:
        conn.execute(
            """
            INSERT INTO seen_jobs (key, title, url, source, first_seen, last_seen, score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scored.key,
                scored.item.title,
                scored.item.url,
                scored.item.source,
                now,
                now,
                scored.retrieval_score,
            ),
        )
    else:
        existing_key = row[0]
        conn.execute(
            """
            UPDATE seen_jobs
            SET key = ?, title = ?, url = ?, source = ?, last_seen = ?, score = ?
            WHERE key = ?
            """,
            (
                scored.key,
                scored.item.title,
                scored.item.url,
                scored.item.source,
                now,
                scored.retrieval_score,
                existing_key,
            ),
        )
    return replace(scored, is_new=is_new)


def local_calendar_date(value: str) -> dt.date | None:
    """Return an ISO timestamp's date in the machine's local timezone."""
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return parse_iso_date(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed.date()


def read_seen_retrieval_score(
    conn: sqlite3.Connection, key: str
) -> int | None:
    """Read the v1 ``score`` column using its v2 retrieval_score meaning."""
    row = conn.execute("SELECT score FROM seen_jobs WHERE key = ?", (key,)).fetchone()
    return int(row[0]) if row is not None else None


def reject_symlinks(path: Path) -> None:
    try:
        # Keeps the macOS /var and /tmp system aliases allowed.
        common_paths.reject_symlinks(path.expanduser())
    except common_paths.PathPolicyError as error:
        raise ValueError(f"symbolic links are not allowed in collector paths: {error.path}") from None


def configured_path(profile_path: Path, value: str) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = profile_path.parent / candidate
    reject_symlinks(candidate)
    return candidate.resolve()


def fixture_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value.strip() or Path(value).is_absolute():
        raise ValueError("fixture paths must be relative files inside the fixture directory")
    path = configured_path(root / "sources.json", value)
    if not path.is_relative_to(root.resolve()):
        raise ValueError("fixture paths must remain inside the fixture directory")
    return path


def require_runtime_path(path: Path) -> None:
    """Check even when output parent directories do not exist yet."""
    reject_symlinks(path)
    try:
        common_paths.require_private_path(path, allow_outside_git=True)
    except common_paths.PathPolicyError as error:
        raise ValueError(f"runtime material must be ignored and untracked, or outside Git: {error.path}") from None


def atomic_write(path: Path, text: str) -> None:
    reject_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
