"""Retrieval scoring, requirement classification and configured exclusions."""
from __future__ import annotations

import datetime as dt
import re

from radar import RequirementEvidence
from collect_base import (
    JobItem, clean_text, html_to_text, matching_terms, normalize_for_match, normalize_quotes,
    parse_iso_date,
)


def extract_minimum_years_experience(text: str) -> int | None:
    """Extract explicit required experience, excluding preferred/nice-to-have text."""
    patterns = [
        r"(?:at least|minimum(?: of)?|min\.?|more than|over)\s+(\d+)\+?\s+years",
        r"(\d+)(?:\s*-\s*\d+)?\+?\s+years(?:'|\s+of)?\s+"
        r"(?:relevant\s+|professional\s+|work\s+|industry\s+)?experience",
        r"(?:经验|工作经验)\s*(\d+)\s*年(?:以上|及以上)",
        r"(\d+)\s*年(?:以上|及以上)(?:相关)?(?:工作)?经验",
    ]
    values: list[int] = []
    for segment in requirement_segments(text):
        normalized = normalize_for_match(segment)
        if requirement_kind(segment) in {"preferred", "nice_to_have"}:
            continue
        for pattern in patterns:
            values.extend(
                int(match.group(1)) for match in re.finditer(pattern, normalized)
            )
    return min(values) if values else None


def requirement_segments(text: str) -> list[str]:
    normalized = normalize_quotes(html_to_text(text or ""))
    normalized = re.sub(
        r"(?i)(?=\b(?:minimum|required|preferred|nice to have|nice-to-have|bonus)"
        r"\s+(?:qualifications?|requirements?)\b)",
        "\n",
        normalized,
    )
    parts = re.split(r"[\n\r]+|(?<=[.;。；])\s+", normalized)
    return [clean_text(part).lstrip("-*• ") for part in parts if clean_text(part)]


def requirement_kind(segment: str) -> str:
    normalized = normalize_for_match(segment)
    if matching_terms(
        normalized,
        [
            "nice to have",
            "nice-to-have",
            "bonus",
            "a plus",
            "plus but not required",
            "加分项",
            "加分",
        ],
    ):
        return "nice_to_have"
    if matching_terms(
        normalized,
        [
            "preferred",
            "ideally",
            "优先考虑",
            "优先",
        ],
    ):
        return "preferred"
    if matching_terms(
        normalized,
        [
            "required",
            "must have",
            "must be",
            "minimum",
            "at least",
            "requirement",
            "任职要求",
            "岗位要求",
            "必须",
            "需具备",
            "至少",
        ],
    ):
        return "required"
    return "unclassified"


def classify_requirement_evidence(text: str) -> RequirementEvidence:
    buckets: dict[str, list[str]] = {
        "required": [],
        "preferred": [],
        "nice_to_have": [],
        "unclassified": [],
    }
    for segment in requirement_segments(text):
        buckets[requirement_kind(segment)].append(segment)
    return RequirementEvidence(
        required=tuple(buckets["required"]),
        preferred=tuple(buckets["preferred"]),
        nice_to_have=tuple(buckets["nice_to_have"]),
        unclassified=tuple(buckets["unclassified"]),
    )


def item_search_text(item: JobItem) -> str:
    return " ".join(
        str(value)
        for value in [
            item.title,
            item.snippet,
            item.url,
            item.company,
            item.location,
            item.employment_type,
            item.position_level,
        ]
        if value
    )


def discovery_domain_hints(profile: dict) -> list[str]:
    """Return discovery hints, including the v1 config name as a read-only alias."""
    if profile.get("discovery_domain_hints") is not None:
        return list(profile.get("discovery_domain_hints") or [])
    queue_config = profile.get("application_queue", {})
    if queue_config.get("discovery_domain_hints") is not None:
        return list(queue_config.get("discovery_domain_hints") or [])
    return list(queue_config.get("required_domain_keywords") or [])


def score_item(item: JobItem, source: dict, profile: dict) -> tuple[int, tuple[str, ...]]:
    haystack = normalize_for_match(item_search_text(item))
    score = int(source.get("priority", 0))
    reasons: list[str] = []
    if score:
        reasons.append(f"source +{score}")

    role_hits = matching_terms(haystack, profile.get("target_roles", []))
    if role_hits:
        score += 25
        reasons.append("role: " + ", ".join(role_hits[:3]))

    must_hits = matching_terms(haystack, profile.get("must_include_any", []))
    if must_hits:
        score += 20
        reasons.append("core: " + ", ".join(must_hits[:4]))

    preferred_hits = matching_terms(haystack, profile.get("preferred_keywords", []))
    if preferred_hits:
        bonus = min(30, 5 * len(preferred_hits))
        score += bonus
        reasons.append(f"keywords +{bonus}: " + ", ".join(preferred_hits[:5]))

    domain_hits = matching_terms(haystack, discovery_domain_hints(profile))
    if domain_hits:
        bonus = min(12, 3 * len(domain_hits))
        score += bonus
        reasons.append(f"discovery hints +{bonus}: " + ", ".join(domain_hits[:4]))

    fresh_haystack = normalize_for_match(
        f"{item.title} {item.employment_type} {item.position_level}"
    )
    fresh_hits = matching_terms(
        fresh_haystack, profile.get("fresh_grad_keywords", [])
    )
    if fresh_hits:
        score += 20
        reasons.append("fresh grad: " + ", ".join(fresh_hits[:3]))

    location_hits = matching_terms(haystack, profile.get("locations", []))
    if location_hits:
        score += 15
        reasons.append("location: " + ", ".join(location_hits[:3]))

    non_target_location_hits = matching_terms(haystack, profile.get("non_target_locations", []))
    if non_target_location_hits and not location_hits:
        score -= 35
        reasons.append("non-target location -35: " + ", ".join(non_target_location_hits[:3]))

    company_hits = matching_terms(haystack, profile.get("target_companies", []))
    if company_hits:
        score += 10
        reasons.append("company: " + ", ".join(company_hits[:3]))

    negative_hits = matching_terms(haystack, profile.get("negative_keywords", []))
    if negative_hits:
        penalty = min(80, 25 * len(negative_hits))
        score -= penalty
        reasons.append(f"negative -{penalty}: " + ", ".join(negative_hits[:4]))

    generic_hits = generic_title_hits(item.title, profile.get("generic_link_titles", []))
    if generic_hits:
        score -= 35
        reasons.append("generic link -35: " + ", ".join(generic_hits[:3]))

    return max(0, score), tuple(reasons)


def generic_title_hits(title: str, terms: list[str]) -> list[str]:
    normalized_title = normalize_for_match(title)
    if "{{" in normalized_title or "}}" in normalized_title:
        return ["template text"]
    hits: list[str] = []
    for term in terms:
        normalized = normalize_for_match(term)
        if normalized and normalized_title == normalized:
            hits.append(term)
    return hits


def configured_exclusion_reasons(item: JobItem, profile: dict) -> tuple[str, ...]:
    """Retain configured discovery filters as review hints, not an assessment."""
    haystack = normalize_for_match(item_search_text(item))
    reasons = []
    internship = matching_terms(normalize_for_match(
        f"{item.title} {item.employment_type}"), profile.get("internship_keywords", []))
    locations = matching_terms(haystack, profile.get("internship_excluded_locations", []))
    if internship and locations:
        reasons.append("Configured internship exclusion: " + ", ".join(locations))
    allowed = set(profile.get("allowed_graduation_years", []))
    if allowed:
        for year in sorted(set(re.findall(r"(20\d{2})\s*届", haystack))):
            if year not in allowed:
                reasons.append("Configured graduation year mismatch: " + year)
    for label, terms in (("Excluded keyword", profile.get("blocked_keywords", [])),
                         ("Excluded location", profile.get("non_target_locations", []))):
        hits = matching_terms(haystack, terms)
        if hits:
            reasons.append(label + ": " + ", ".join(hits))
    expires = parse_iso_date(item.expires)
    if expires and expires < dt.date.today():
        reasons.append("Posting reports an expired deadline: " + item.expires)
    return tuple(reasons)
