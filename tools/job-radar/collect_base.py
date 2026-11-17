"""Shared collector records and text, date and URL helpers."""
from __future__ import annotations

import datetime as dt
import html
import re
import urllib.parse
from dataclasses import dataclass

import radar


@dataclass(frozen=True)
class ScoredItem:
    item: JobItem
    retrieval_score: int
    reasons: tuple[str, ...]
    key: str
    is_new: bool = True
    detail: JobDetail | None = None
    blocked_reasons: tuple[str, ...] = ()
    dossier: radar.JobDossier | None = None


@dataclass(frozen=True)
class JobItem:
    title: str
    url: str
    source: str
    snippet: str = ""
    published: str = ""
    company: str = ""
    location: str = ""
    employment_type: str = ""
    position_level: str = ""
    minimum_years_experience: int | None = None
    expires: str = ""
    jd: str = ""
    requirements: str = ""
    job_id: str = ""
    source_type: str = ""
    role_level: bool = False


@dataclass(frozen=True)
class JobDetail:
    apply_url: str
    jd: str
    requirements: str
    status: str = ""
    title_matches: bool = False
    apply_action_found: bool = False
    is_fallback: bool = False


clean_text = radar.clean_text


def normalize_for_match(value: str) -> str:
    return normalize_quotes(clean_text(value)).lower()


def normalize_quotes(value: str) -> str:
    return (
        value.replace("’", "'")
        .replace("‘", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("–", "-")
        .replace("—", "-")
    )


def sanitize_url(url: str) -> str:
    return urllib.parse.quote(url.strip(), safe=":/?&=%#[]@!$'()*+,;")


def source_url(source: dict) -> str:
    if source.get("type") == "wechat_search":
        query = source.get("query", "")
        return "https://weixin.sogou.com/weixin?type=2&query=" + urllib.parse.quote(query)
    return source.get("url", "")


def join_mapping_values(values: object, key: str) -> str:
    if not isinstance(values, list):
        return ""
    return ", ".join(
        clean_text(value.get(key) or "")
        for value in values
        if isinstance(value, dict) and value.get(key)
    )


def optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def structured_snippet(
    company: object, location: object, employment_type: object, description: str
) -> str:
    return clean_text(
        "; ".join(
            part
            for part in [
                clean_text(str(company or "")),
                clean_text(str(location or "")),
                clean_text(str(employment_type or "")),
                compact_excerpt(description, 1200),
            ]
            if part
        )
    )


def iso_date(value: object) -> str:
    text = clean_text(str(value or ""))
    match = re.match(r"\d{4}-\d{2}-\d{2}", text)
    return match.group(0) if match else text


def epoch_millis_date(value: object) -> str:
    try:
        timestamp = int(value) / 1000
    except (TypeError, ValueError):
        return ""
    return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).date().isoformat()


def first_text_value(row: dict, keys: list[str]) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, list):
            parts = [
                clean_text(
                    str(
                        (part.get("name") or part.get("label") or "")
                        if isinstance(part, dict)
                        else part or ""
                    )
                )
                for part in value
            ]
            if any(parts):
                return ", ".join(part for part in parts if part)
        if isinstance(value, dict):
            value = value.get("name") or value.get("label") or ""
        if value:
            return clean_text(str(value))
    return ""


def extract_job_id(url: object) -> str:
    text = clean_text(str(url or ""))
    if not text:
        return ""
    parsed = urllib.parse.urlsplit(text)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    for key in [
        "jobId",
        "job_id",
        "jobid",
        "positionId",
        "position_id",
        "postingId",
        "requisitionId",
        "gh_jid",
    ]:
        value = clean_text(query.get(key) or "")
        if value:
            return value
    if parsed.fragment and normalize_for_match(parsed.fragment) not in {
        "jobs",
        "joblist",
        "jobslist",
        "positions",
    }:
        return clean_text(parsed.fragment)

    segments = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    markers = {"apply", "application", "detail", "job", "jobs", "position", "positions", "posting", "postings", "role", "roles"}
    ignored = markers | {"campus", "graduate", "graduates", "list", "search", "home"}
    for index, segment in enumerate(segments):
        if normalize_for_match(segment) not in markers:
            continue
        for candidate in reversed(segments[index + 1 :]):
            if normalize_for_match(candidate) not in ignored:
                return clean_text(candidate)
    return ""


def is_direct_application_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    path = normalize_for_match(parsed.path)
    return bool(
        re.search(r"/(?:apply|application)(?:/|$)", path)
        or any(key.lower() in {"gh_jid", "jobid", "positionid"} for key, _ in urllib.parse.parse_qsl(parsed.query))
    )


def is_direct_role_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlsplit(url)
    path = normalize_for_match(parsed.path).rstrip("/")
    if is_direct_application_url(url) or extract_job_id(url):
        return True
    return bool(
        re.search(
            r"/(?:jobs?|positions?|postings?|roles?)/(?!list(?:/|$)|search(?:/|$)|home(?:/|$))[^/]+$",
            path,
        )
    )


def parse_iso_date(value: str) -> dt.date | None:
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    if not match:
        return None
    try:
        return dt.date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def matching_terms(haystack: str, terms: list[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        normalized = normalize_for_match(term)
        if normalized and term_matches(haystack, normalized):
            hits.append(term)
    return hits


def term_matches(haystack: str, normalized_term: str) -> bool:
    if re.fullmatch(r"[a-z0-9][a-z0-9 +.,/-]*", normalized_term):
        return re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", haystack) is not None
    return normalized_term in haystack


def html_to_text(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|section|article|li|ul|ol|h[1-6])>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def compact_excerpt(text: str, limit: int) -> str:
    text = clean_text(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."

def require_http_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("source and detail URLs must be HTTP(S) without embedded credentials")
    return url
