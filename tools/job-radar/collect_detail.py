"""Job detail page extraction; fetching stays in collect.py."""
from __future__ import annotations

import json
import re
import urllib.parse

import radar
from collect_base import (
    JobDetail, JobItem, clean_text, compact_excerpt, html_to_text, is_direct_application_url,
    normalize_for_match, normalize_quotes,
)


def parse_job_detail(item: JobItem, text: str, profile: dict) -> JobDetail:
    description_html = extract_embedded_description_html(text)
    page_text = html_to_text(description_html or text)
    sections = profile.get("detail_sections", {})
    jd = extract_section(
        page_text,
        sections.get("jd_headings", []),
        sections.get("requirements_headings", []) + sections.get("stop_headings", []),
    )
    requirements = extract_section(
        page_text,
        sections.get("requirements_headings", []),
        sections.get("stop_headings", []),
    )
    if not jd:
        jd = compact_excerpt(page_text, 700)
    if not requirements:
        requirements = extract_requirement_sentences(page_text)
    apply_url = extract_apply_url(item.url, text)
    return JobDetail(
        apply_url=apply_url or item.url,
        jd=compact_excerpt(jd, 900),
        requirements=compact_excerpt(requirements, 700),
        title_matches=title_matches_page(item, page_text),
        apply_action_found=bool(apply_url) or is_direct_application_url(item.url),
    )


def title_matches_page(item: JobItem, page_text: str) -> bool:
    title = radar.normalize_for_match(item.title)
    for removable in (item.company, item.location):
        if removable:
            title = title.replace(radar.normalize_for_match(removable), " ")
    title = "".join(character for character in title if character.isalnum())
    if len(title) < 5:
        return False
    normalized_page = "".join(character for character in radar.normalize_for_match(page_text)
                              if character.isalnum())
    return title in normalized_page


def extract_embedded_description_html(text: str) -> str:
    match = re.search(r'"descriptionHtml"\s*:\s*"((?:\\.|[^"\\])*)"', text)
    if not match:
        return ""
    try:
        return json.loads(f'"{match.group(1)}"')
    except json.JSONDecodeError:
        return ""


def extract_section(text: str, start_headings: list[str], stop_headings: list[str]) -> str:
    lowered = normalize_quotes(text).lower()
    starts = [
        (lowered.find(normalize_quotes(heading).lower()), heading)
        for heading in start_headings
        if normalize_quotes(heading).lower() in lowered
    ]
    starts = [(index, heading) for index, heading in starts if index >= 0]
    if not starts:
        return ""
    start, heading = min(starts, key=lambda row: row[0])
    section_start = start + len(heading)
    stop_candidates = [
        lowered.find(normalize_quotes(stop).lower(), section_start)
        for stop in stop_headings
        if normalize_quotes(stop).lower() in lowered[section_start:]
    ]
    stop_candidates = [index for index in stop_candidates if index > section_start]
    section_end = min(stop_candidates) if stop_candidates else min(len(text), section_start + 2500)
    return text[section_start:section_end].strip(" :-\n\t")


def extract_requirement_sentences(text: str) -> str:
    keywords = [
        "experience",
        "proficiency",
        "familiar",
        "knowledge",
        "ability",
        "sql",
        "python",
        "llm",
        "agent",
        "requirement",
        "work authorization",
        "right to work",
        "work permit",
        "sponsorship",
        "visa",
        "要求",
        "经验",
        "熟悉",
        "能力",
        "工签",
        "签证",
        "工作许可",
    ]
    lines = [clean_text(line) for line in text.splitlines()]
    hits = [line for line in lines if len(line) >= 25 and any(word in line.lower() for word in keywords)]
    return "\n".join(hits[:8])


def extract_apply_url(base_url: str, text: str) -> str:
    apply_terms = ["apply", "submit application", "申请", "投递", "立即申请", "立即投递"]
    anchor_pattern = re.compile(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>")
    for href, label_html in anchor_pattern.findall(text):
        label = normalize_for_match(html_to_text(label_html))
        if any(term in label for term in apply_terms):
            return urllib.parse.urljoin(base_url, href)
    return ""
