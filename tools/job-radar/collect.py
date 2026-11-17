#!/usr/bin/env python3
"""Foreground source collection migrated from Job Radar; never writes the queue.

--sources explicitly enables HTTP fetching. --fixtures exercises the same
parsers using fictional local payloads. --dry-run suppresses all persistence,
not network requests. Candidate evidence remains pending Agent review.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import closing
from dataclasses import asdict, dataclass, replace
from html.parser import HTMLParser
from pathlib import Path

# The preview command must not create a local module-cache directory either.
sys.dont_write_bytecode = True
# The sibling collect_* modules must import even when this file is loaded by path.
COLLECT_DIR = Path(__file__).resolve().parent
if str(COLLECT_DIR) not in sys.path:
    sys.path.insert(0, str(COLLECT_DIR))
import radar
from radar import RequirementEvidence
from haojob_common import paths as common_paths
from collect_base import (  # noqa: F401 - re-exported for existing callers
    ScoredItem,
    JobItem,
    JobDetail,
    clean_text,
    normalize_for_match,
    normalize_quotes,
    sanitize_url,
    source_url,
    join_mapping_values,
    optional_int,
    structured_snippet,
    iso_date,
    epoch_millis_date,
    first_text_value,
    extract_job_id,
    is_direct_application_url,
    is_direct_role_url,
    parse_iso_date,
    matching_terms,
    term_matches,
    html_to_text,
    compact_excerpt,
    require_http_url,
)
from collect_scoring import (  # noqa: F401 - re-exported for existing callers
    extract_minimum_years_experience,
    requirement_segments,
    requirement_kind,
    classify_requirement_evidence,
    item_search_text,
    discovery_domain_hints,
    score_item,
    generic_title_hits,
    configured_exclusion_reasons,
)
from collect_detail import (  # noqa: F401 - re-exported for existing callers
    parse_job_detail,
    title_matches_page,
    extract_embedded_description_html,
    extract_section,
    extract_requirement_sentences,
    extract_apply_url,
)
from collect_sources import (  # noqa: F401 - re-exported for existing callers
    LinkExtractor,
    is_probably_recruiting_link,
    is_probably_recruiting_title,
    parse_html_items,
    parse_wechat_search_items,
    parse_rss_items,
    parse_mycareersfuture_items,
    parse_ashby_items,
    parse_greenhouse_items,
    parse_lever_items,
    parse_baidu_campus_items,
    source_accepts_item,
    parse_payload,
)
from collect_store import (  # noqa: F401 - re-exported for existing callers
    load_source_health,
    save_source_health,
    update_source_health,
    init_db,
    mark_seen,
    local_calendar_date,
    read_seen_retrieval_score,
    reject_symlinks,
    configured_path,
    fixture_path,
    require_runtime_path,
    atomic_write,
)
from collect_report import (  # noqa: F401 - re-exported for existing callers
    render_digest,
)

load_json = radar.load_json
SOURCE_TYPES = {"html", "rss", "ashby", "greenhouse", "lever", "mycareersfuture",
                "baidu_campus", "wechat_search", "portal", "manual"}
DEFAULT_COLLECTOR = {
    "database_path": "radar/seen_jobs.sqlite3",
    "source_health_path": "radar/source_health.json",
    "reports_dir": "radar/reports",
    "dossiers_path": "radar/dossiers.json",
    "timeout_seconds": 20,
    "max_details": 20,
    "detail_minimum_score": 0,
    "report_minimum_score": 0,
}


def fetch_job_detail(item: JobItem, timeout: int, profile: dict) -> JobDetail:
    return parse_job_detail(item, fetch_text(item.url, timeout), profile)


def fetch_text(url: str, timeout: int) -> str:
    request = urllib.request.Request(sanitize_url(require_http_url(url)), headers={
        "User-Agent": "JobWorkspaceRadar/1.0 (local foreground collection)",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    return raw.decode(match.group(1) if match else "utf-8", errors="replace")


def collect_from_source(source: dict, timeout: int,
                        fixture_root: Path | None = None) -> tuple[list[JobItem], str | None]:
    if not source.get("enabled", True) or source.get("type") == "manual":
        return [], None
    if source.get("type") == "portal":
        return [JobItem(title=source.get("title") or source["name"],
                        url=source_url(source), source=source["name"],
                        snippet=source.get("snippet", ""), company=source.get("company", ""),
                        location=source.get("location", ""),
                        employment_type=source.get("employment_type", ""),
                        jd=source.get("jd", ""), requirements=source.get("requirements", ""),
                        job_id=source.get("job_id", ""), source_type="portal",
                        role_level=bool(source.get("role_level", False)))], None
    try:
        if fixture_root is not None:
            text = fixture_path(fixture_root, source["fixture_path"]).read_text(encoding="utf-8")
        else:
            text = fetch_text(source_url(source), timeout)
        return parse_payload(source, text), None
    except (OSError, ValueError, TypeError, KeyError, ET.ParseError) as error:
        return [], f"{source['name']}: {type(error).__name__}: {error}"


def item_key(item: JobItem) -> str:
    identity = radar.JobIdentity(item.company, item.title, item.job_id, item.url,
                                 item.location, item.employment_type, "UNKNOWN")
    if item.job_id:
        key = "id:" + radar.normalize_company(item.company or item.source) + "\0" + item.job_id
    else:
        key = radar.semantic_job_fingerprint(identity) or radar.normalize_url(item.url)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def attach_dossier(row: ScoredItem, fetched_at: str) -> ScoredItem:
    item = row.item
    requirements = row.detail.requirements if row.detail else item.requirements
    reasons = ("Collected source evidence requires official posting review.",) + row.blocked_reasons
    dossier = radar.JobDossier(
        job_identity=radar.JobIdentity(item.company, item.title, item.job_id, item.url,
                                       item.location, item.employment_type, "UNKNOWN"),
        verification=radar.JobVerification("PENDING", reasons),
        feasibility=radar.FeasibilityAssessment("UNKNOWN", unknowns=(
            "Review current eligibility and the user's confirmed conditions.",)),
        capability_match=radar.CapabilityMatch(), strategic_priority=radar.StrategicPriority(),
        application_route=radar.ApplicationRoute(),
        recommendation=radar.Recommendation("MANUAL_REVIEW", (
            "Collection and retrieval score do not establish fit or application priority.",)),
        provenance=radar.Provenance(fetched_at, item.source, "job-radar-collector", "2.0"),
        requirements=classify_requirement_evidence(requirements),
    )
    return replace(row, dossier=dossier)


def enrich_details(rows: list[ScoredItem], sources: list[dict], profile: dict,
                   config: dict, fixture_root: Path | None = None,
                   no_details: bool = False) -> tuple[list[ScoredItem], list[str]]:
    enriched, errors = [], []
    source_map = {source["name"]: source for source in sources}
    fetched = 0
    for row in rows:
        item = row.item
        detail = None
        if item.jd or item.requirements:
            detail = JobDetail(item.url, item.jd or item.snippet, item.requirements,
                               status="Structured source evidence; unverified")
        elif (not no_details and item.source_type not in {"portal", "wechat_search"}
              and row.retrieval_score >= config["detail_minimum_score"]
              and fetched < config["max_details"]):
            try:
                if fixture_root is None:
                    fetched += 1
                    detail = fetch_job_detail(item, config["timeout_seconds"], profile)
                else:
                    fixture = source_map[item.source].get("detail_fixtures", {}).get(item.url)
                    if fixture:
                        fetched += 1
                        text = fixture_path(fixture_root, fixture).read_text(encoding="utf-8")
                        detail = parse_job_detail(item, text, profile)
            except (OSError, ValueError, TypeError) as error:
                errors.append(f"{item.source} detail: {type(error).__name__}: {error}")
        enriched.append(replace(row, detail=detail))
    return enriched, errors


def collect_all(sources: list[dict], profile: dict, config: dict,
                fetched_at: str, fixture_root: Path | None = None,
                no_details: bool = False) -> tuple[list[ScoredItem], list[str], dict[str, int]]:
    rows, errors, counts = [], [], {}
    for source in sources:
        items, error = collect_from_source(source, config["timeout_seconds"], fixture_root)
        if error:
            errors.append(error)
        counts[source["name"]] = len(items)
        for item in items:
            score, reasons = score_item(item, source, profile)
            rows.append(ScoredItem(item, score, reasons, item_key(item),
                                   blocked_reasons=configured_exclusion_reasons(item, profile)))
    rows, detail_errors = enrich_details(rows, sources, profile, config, fixture_root, no_details)
    errors.extend(detail_errors)
    rows = [attach_dossier(row, fetched_at) for row in rows]
    rows.sort(key=lambda row: (bool(row.detail), row.retrieval_score), reverse=True)
    selected = {id(dossier) for dossier in radar.deduplicate_dossiers([row.dossier for row in rows])}
    return [row for row in rows if id(row.dossier) in selected], errors, counts


def utc_now() -> dt.datetime:
    return dt.datetime.now(tz=dt.timezone.utc)


def validate_inputs(profile: object, payload: object, fixtures: bool) -> tuple[dict, list[dict]]:
    if not isinstance(profile, dict) or not isinstance(profile.get("collector", {}), dict):
        raise ValueError("profile and collector must be objects")
    if not isinstance(profile.get("application_queue", {}), dict):
        raise ValueError("application_queue must be an object")
    for name in ("target_roles", "locations", "target_companies", "discovery_domain_hints",
                 "allowed_graduation_years", "internship_excluded_locations", "must_include_any",
                 "preferred_keywords", "fresh_grad_keywords", "negative_keywords", "non_target_locations",
                 "generic_link_titles", "blocked_keywords", "internship_keywords"):
        value = profile.get(name, [])
        if not isinstance(value, list) or any(not isinstance(term, str) for term in value):
            raise ValueError(f"profile.{name} must be a string list")
    sections = profile.get("detail_sections", {})
    if not isinstance(sections, dict):
        raise ValueError("detail_sections must be an object")
    for name in ("jd_headings", "requirements_headings", "stop_headings"):
        value = sections.get(name, [])
        if not isinstance(value, list) or any(not isinstance(term, str) for term in value):
            raise ValueError(f"detail_sections.{name} must be a string list")
    config = {**DEFAULT_COLLECTOR, **profile.get("collector", {})}
    for name in ("timeout_seconds", "max_details", "detail_minimum_score", "report_minimum_score"):
        value = config[name]
        if isinstance(value, bool) or not isinstance(value, int) or value < (1 if name == "timeout_seconds" else 0):
            raise ValueError(f"collector.{name} must be an integer in its allowed range")
    for name in ("database_path", "source_health_path", "reports_dir", "dossiers_path"):
        if not isinstance(config[name], str) or not config[name].strip():
            raise ValueError(f"collector.{name} must be a file path")
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), list):
        raise ValueError("source configuration must contain a sources list")
    names = set()
    for source in payload["sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("name"), str) or not source["name"].strip():
            raise ValueError("each source must have a non-empty name")
        if source["name"] in names:
            raise ValueError("source names must be unique")
        names.add(source["name"])
        if not isinstance(source.get("type", "html"), str) or source.get("type", "html") not in SOURCE_TYPES:
            raise ValueError("unsupported source type")
        if not isinstance(source.get("enabled", True), bool):
            raise ValueError("source.enabled must be a boolean")
        priority = source.get("priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError("source.priority must be an integer")
        for key in ("url", "title", "company", "location", "employment_type", "snippet", "jd",
                    "requirements", "job_id", "query"):
            if not isinstance(source.get(key, ""), str):
                raise ValueError(f"source.{key} must be a string")
        for key in ("require_location_any", "require_title_any", "require_title_all", "require_any"):
            value = source.get(key, [])
            if not isinstance(value, list) or any(not isinstance(term, str) for term in value):
                raise ValueError(f"source.{key} must be a string list")
        details = source.get("detail_fixtures", {})
        if not isinstance(details, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                                for k, v in details.items()):
            raise ValueError("detail_fixtures must map URL strings to relative fixture paths")
        if not source.get("enabled", True) or source.get("type") == "manual":
            continue
        if source.get("type") == "wechat_search" and not source.get("query", "").strip():
            raise ValueError("wechat_search needs an explicit non-empty query")
        require_http_url(source_url(source))
        if fixtures and source.get("type") != "portal" and not isinstance(source.get("fixture_path"), str):
            raise ValueError("each enabled fixture source needs fixture_path")
    return config, payload["sources"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, type=Path)
    source_input = parser.add_mutually_exclusive_group(required=True)
    source_input.add_argument("--sources", type=Path, help="Explicit HTTP(S) collection from configured sources")
    source_input.add_argument("--fixtures", type=Path, help="Offline source payloads; never fetch HTTP")
    parser.add_argument("--dry-run", action="store_true", help="No database, health, report, dossier or directory writes; --sources may still use network")
    parser.add_argument("--include-seen", action="store_true")
    parser.add_argument("--no-details", action="store_true")
    args = parser.parse_args(argv)
    try:
        source_path = args.sources or args.fixtures
        reject_symlinks(args.profile)
        reject_symlinks(source_path)
        profile = load_json(args.profile)
        config, sources = validate_inputs(profile, load_json(source_path), args.fixtures is not None)
        paths = {key: configured_path(args.profile, config[key]) for key in
                 ("database_path", "source_health_path", "reports_dir", "dossiers_path")}
        observed_at = utc_now()
        today = observed_at.astimezone().date().isoformat()
        report_path = paths["reports_dir"] / f"{today}_Job_Radar.md"
        outputs = [paths["database_path"], paths["source_health_path"], paths["dossiers_path"], report_path]
        inputs = {args.profile.resolve(), source_path.resolve()}
        if args.fixtures:
            fixture_root = source_path.resolve().parent
            for source in sources:
                if not source.get("enabled", True) or source.get("type") in {"portal", "manual"}:
                    continue
                inputs.add(fixture_path(fixture_root, source["fixture_path"]))
                for value in source.get("detail_fixtures", {}).values():
                    inputs.add(fixture_path(fixture_root, value))
        queue_config = profile.get("application_queue", {})
        for key in ("path", "application_history_path"):
            if queue_config.get(key):
                inputs.add(configured_path(args.profile, queue_config[key]))
        if len(set(outputs)) != len(outputs) or set(outputs) & inputs:
            raise ValueError("collector outputs must be distinct from each other and configuration/queue/history inputs")
        if any(path.exists() and not path.is_file() for path in outputs):
            raise ValueError("collector output files must not point to directories")
        if paths["reports_dir"].exists() and not paths["reports_dir"].is_dir():
            raise ValueError("collector reports_dir must be a directory")
        if not args.dry_run:
            for path in [*outputs, paths["reports_dir"], args.profile.resolve(), source_path.resolve()]:
                require_runtime_path(path)
        now = observed_at.isoformat()
        rows, errors, counts = collect_all(sources, profile, config, now,
                                         source_path.resolve().parent if args.fixtures else None,
                                         args.no_details)
        if args.dry_run:
            health = {"sources": {}}
        else:
            # Source errors are isolated; one failed source does not discard other leads.
            source_errors = [error for error in errors if any(error.startswith(s["name"] + ":") for s in sources)]
            health = update_source_health(paths["source_health_path"], sources, source_errors,
                                          now=observed_at.astimezone())
            with closing(init_db(paths["database_path"])) as connection:
                with connection:
                    rows = [mark_seen(connection, row, now) for row in rows]
        visible = [row for row in rows if args.include_seen or row.is_new]
        report = render_digest(visible, errors, counts, health, today, config["report_minimum_score"])
        dossiers = [asdict(row.dossier) for row in visible]
        if args.dry_run:
            print(report)
            print(json.dumps({"dossiers": dossiers, "writes_enabled": False}, ensure_ascii=False, indent=2))
        else:
            atomic_write(report_path, report)
            atomic_write(paths["dossiers_path"], json.dumps(dossiers, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"collected_count": len(rows), "visible_count": len(visible),
                          "source_error_count": len(errors), "queue_added": 0,
                          "writes_enabled": not args.dry_run}, ensure_ascii=False))
        return 2 if errors else 0
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
