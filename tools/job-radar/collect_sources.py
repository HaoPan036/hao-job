"""Source payload parsers for the configured source types."""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from collect_base import (
    JobItem, clean_text, compact_excerpt, epoch_millis_date, extract_job_id, first_text_value,
    html_to_text, is_direct_role_url, iso_date, join_mapping_values, matching_terms,
    normalize_for_match, optional_int, sanitize_url, source_url, structured_snippet,
)
from collect_scoring import extract_minimum_years_experience, item_search_text
from collect_detail import extract_requirement_sentences


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {name.lower(): value for name, value in attrs}
        href = attr_map.get("href")
        if not href:
            return
        self._href = urllib.parse.urljoin(self.base_url, href)
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._href:
            return
        text = clean_text(" ".join(self._text))
        if text and is_probably_recruiting_link(text, self._href):
            self.links.append((text, self._href))
        self._href = None
        self._text = []


def is_probably_recruiting_link(title: str, url: str) -> bool:
    # A careers hostname alone must not turn /about and /privacy into job links.
    haystack = normalize_for_match(f"{title} {urllib.parse.urlsplit(url).path}")
    signals = [
        "job",
        "career",
        "position",
        "campus",
        "graduate",
        "intern",
        "recruit",
        "招聘",
        "校招",
        "岗位",
        "职位",
        "实习",
    ]
    return any(signal in haystack for signal in signals)


def is_probably_recruiting_title(title: str) -> bool:
    haystack = normalize_for_match(title)
    signals = [
        "招聘",
        "校招",
        "校园招聘",
        "实习",
        "岗位",
        "职位",
        "内推",
        "投递",
        "网申",
        "提前批",
        "宣讲",
        "秋招",
        "春招",
        "offer",
    ]
    return any(signal in haystack for signal in signals)


def parse_html_items(source: dict, text: str) -> list[JobItem]:
    parser = LinkExtractor(source_url(source))
    parser.feed(text)
    seen: set[str] = set()
    items: list[JobItem] = []
    for title, url in parser.links:
        key = f"{title}\0{url}"
        if key in seen:
            continue
        seen.add(key)
        items.append(
            JobItem(
                title=title,
                url=url,
                source=source["name"],
                company=source.get("company", ""),
                location=source.get("location", ""),
                employment_type=source.get("employment_type", ""),
                job_id=extract_job_id(url),
                source_type=source.get("type", "html"),
                role_level=is_direct_role_url(url),
            )
        )
    return items


def parse_wechat_search_items(source: dict, text: str) -> list[JobItem]:
    base_url = source_url(source)
    items: list[JobItem] = []
    seen: set[str] = set()
    result_pattern = re.compile(r'(?is)<div class="txt-box">\s*<h3>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<p class="txt-info"[^>]*>(.*?)</p>(.*?)</div>')
    for href, title_html, summary_html, tail_html in result_pattern.findall(text):
        title = html_to_text(title_html)
        summary = html_to_text(summary_html)
        if not is_probably_recruiting_title(title):
            continue
        account_match = re.search(r'(?is)<span class="all-time-y2">(.*?)</span>', tail_html)
        account = html_to_text(account_match.group(1)) if account_match else ""
        url = sanitize_url(urllib.parse.urljoin(base_url, html.unescape(href)))
        key = f"{title}\0{url}"
        if not title or key in seen:
            continue
        snippet = clean_text("；".join(part for part in [summary, f"公众号：{account}" if account else ""] if part))
        candidate = JobItem(
            title=title,
            url=url,
            source=source["name"],
            snippet=snippet,
            company=source.get("company", ""),
            location=source.get("location", ""),
            employment_type=source.get("employment_type", ""),
            source_type="wechat_search",
            role_level=False,
        )
        title_required_terms = source.get("require_title_any", [])
        if title_required_terms and not matching_terms(normalize_for_match(candidate.title), title_required_terms):
            continue
        title_required_all = source.get("require_title_all", [])
        if title_required_all and not all(
            matching_terms(normalize_for_match(candidate.title), [term])
            for term in title_required_all
        ):
            continue
        required_terms = source.get("require_any", [])
        if required_terms and not matching_terms(
            normalize_for_match(f"{candidate.title} {candidate.snippet}"), required_terms
        ):
            continue
        seen.add(key)
        items.append(candidate)
    return items


def parse_rss_items(source: dict, text: str) -> list[JobItem]:
    root = ET.fromstring(text)
    items: list[JobItem] = []
    rss_items = root.findall(".//item")
    atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    for node in rss_items:
        title = clean_text(node.findtext("title") or "")
        link = clean_text(node.findtext("link") or source["url"])
        snippet = clean_text(node.findtext("description") or "")
        published = clean_text(node.findtext("pubDate") or "")
        if title:
            items.append(
                JobItem(
                    title=title,
                    url=link,
                    source=source["name"],
                    snippet=snippet,
                    published=published,
                    company=source.get("company", ""),
                    location=source.get("location", ""),
                    employment_type=source.get("employment_type", ""),
                    job_id=extract_job_id(link),
                    source_type="rss",
                    role_level=is_direct_role_url(link),
                )
            )

    for node in atom_entries:
        title = clean_text(node.findtext("{http://www.w3.org/2005/Atom}title") or "")
        link = source["url"]
        for link_node in node.findall("{http://www.w3.org/2005/Atom}link"):
            href = link_node.attrib.get("href")
            if href:
                link = href
                break
        snippet = clean_text(node.findtext("{http://www.w3.org/2005/Atom}summary") or "")
        published = clean_text(node.findtext("{http://www.w3.org/2005/Atom}updated") or "")
        if title:
            items.append(
                JobItem(
                    title=title,
                    url=link,
                    source=source["name"],
                    snippet=snippet,
                    published=published,
                    company=source.get("company", ""),
                    location=source.get("location", ""),
                    employment_type=source.get("employment_type", ""),
                    job_id=extract_job_id(link),
                    source_type="rss",
                    role_level=is_direct_role_url(link),
                )
            )

    return items


def parse_mycareersfuture_items(source: dict, text: str) -> list[JobItem]:
    payload = json.loads(text)
    items: list[JobItem] = []
    for row in payload.get("results", []):
        metadata = row.get("metadata") or {}
        company = clean_text((row.get("postedCompany") or {}).get("name", ""))
        employment_types = join_mapping_values(row.get("employmentTypes"), "employmentType")
        position_levels = join_mapping_values(row.get("positionLevels"), "position")
        skills = join_mapping_values(row.get("skills"), "skill")
        description = html_to_text(row.get("description") or "")
        minimum_experience = optional_int(row.get("minimumYearsExperience"))
        published = clean_text(metadata.get("newPostingDate") or "")
        expires = clean_text(metadata.get("expiryDate") or "")
        url = clean_text(metadata.get("jobDetailsUrl") or source_url(source))
        location = source.get("location", "Singapore")
        summary_parts = [
            company,
            location,
            employment_types,
            position_levels,
            f"minimum experience: {minimum_experience} years"
            if minimum_experience is not None
            else "",
            f"skills: {skills}" if skills else "",
            compact_excerpt(description, 1200),
        ]
        item = JobItem(
            title=clean_text(row.get("title") or ""),
            url=url,
            source=source["name"],
            snippet=clean_text("; ".join(part for part in summary_parts if part)),
            published=published,
            company=company,
            location=location,
            employment_type=employment_types,
            position_level=position_levels,
            minimum_years_experience=minimum_experience,
            expires=expires,
            jd=compact_excerpt(description, 1800),
            requirements=compact_excerpt(extract_requirement_sentences(description), 1000),
            job_id=clean_text(row.get("uuid") or ""),
            source_type="mycareersfuture",
            role_level=True,
        )
        if item.title and source_accepts_item(source, item):
            items.append(item)
    return items


def parse_ashby_items(source: dict, text: str) -> list[JobItem]:
    payload = json.loads(text)
    items: list[JobItem] = []
    for row in payload.get("jobs", []):
        description = html_to_text(row.get("descriptionHtml") or row.get("description") or "")
        item = JobItem(
            title=clean_text(row.get("title") or ""),
            url=clean_text(row.get("applyUrl") or row.get("jobUrl") or source_url(source)),
            source=source["name"],
            snippet=structured_snippet(
                source.get("company", ""),
                row.get("location", ""),
                row.get("employmentType", ""),
                description,
            ),
            published=iso_date(row.get("publishedAt")),
            company=source.get("company", ""),
            location=clean_text(row.get("location") or ""),
            employment_type=clean_text(row.get("employmentType") or ""),
            minimum_years_experience=extract_minimum_years_experience(description),
            jd=compact_excerpt(description, 1800),
            requirements=compact_excerpt(extract_requirement_sentences(description), 1000),
            job_id=clean_text(row.get("id") or extract_job_id(row.get("jobUrl") or row.get("applyUrl") or "")),
            source_type="ashby",
            role_level=True,
        )
        if item.title and source_accepts_item(source, item):
            items.append(item)
    return items


def parse_greenhouse_items(source: dict, text: str) -> list[JobItem]:
    payload = json.loads(text)
    items: list[JobItem] = []
    for row in payload.get("jobs", []):
        description = html_to_text(row.get("content") or "")
        location = clean_text((row.get("location") or {}).get("name", ""))
        item = JobItem(
            title=clean_text(row.get("title") or ""),
            url=clean_text(row.get("absolute_url") or source_url(source)),
            source=source["name"],
            snippet=structured_snippet(
                source.get("company", ""),
                location,
                source.get("employment_type", ""),
                description,
            ),
            published=iso_date(row.get("updated_at")),
            company=source.get("company", ""),
            location=location,
            employment_type=source.get("employment_type", ""),
            minimum_years_experience=extract_minimum_years_experience(description),
            jd=compact_excerpt(description, 1800),
            requirements=compact_excerpt(extract_requirement_sentences(description), 1000),
            job_id=clean_text(str(row.get("id") or "")),
            source_type="greenhouse",
            role_level=True,
        )
        if item.title and source_accepts_item(source, item):
            items.append(item)
    return items


def parse_lever_items(source: dict, text: str) -> list[JobItem]:
    payload = json.loads(text)
    items: list[JobItem] = []
    for row in payload if isinstance(payload, list) else payload.get("postings", []):
        categories = row.get("categories") or {}
        location = clean_text(categories.get("location") or "")
        employment_type = clean_text(categories.get("commitment") or "")
        list_text = "\n".join(
            html_to_text(f"{entry.get('text', '')}\n{entry.get('content', '')}")
            for entry in row.get("lists", [])
        )
        description = clean_text(
            "\n".join(
                part
                for part in [
                    row.get("descriptionPlain") or "",
                    list_text,
                    row.get("additionalPlain") or "",
                ]
                if part
            )
        )
        item = JobItem(
            title=clean_text(row.get("text") or ""),
            url=clean_text(row.get("hostedUrl") or row.get("applyUrl") or source_url(source)),
            source=source["name"],
            snippet=structured_snippet(
                source.get("company", ""), location, employment_type, description
            ),
            published=epoch_millis_date(row.get("createdAt")),
            company=source.get("company", ""),
            location=location,
            employment_type=employment_type,
            minimum_years_experience=extract_minimum_years_experience(description),
            jd=compact_excerpt(description, 1800),
            requirements=compact_excerpt(extract_requirement_sentences(description), 1000),
            job_id=clean_text(row.get("id") or extract_job_id(row.get("hostedUrl") or row.get("applyUrl") or "")),
            source_type="lever",
            role_level=True,
        )
        if item.title and source_accepts_item(source, item):
            items.append(item)
    return items


def parse_baidu_campus_items(source: dict, text: str) -> list[JobItem]:
    marker = '"listDetailData":'
    marker_index = text.find(marker)
    if marker_index < 0:
        return []
    start = text.find("[", marker_index + len(marker))
    if start < 0:
        return []
    rows, _ = json.JSONDecoder().raw_decode(text[start:])
    items: list[JobItem] = []
    for row in rows:
        location = first_text_value(
            row,
            ["workPlaceName", "workPlace", "workplace", "location", "workCity"],
        )
        title = clean_text(row.get("name") or row.get("postName") or "")
        work_content = clean_text(row.get("workContent") or row.get("description") or "")
        requirements = clean_text(
            row.get("serviceCondition") or row.get("qualification") or ""
        )
        job_id = clean_text(row.get("jobId") or row.get("postId") or "")
        url = source_url(source)
        if job_id:
            url = f"{url}#{urllib.parse.quote(job_id)}"
        item = JobItem(
            title=title,
            url=url,
            source=source["name"],
            snippet=structured_snippet(
                source.get("company", "百度"),
                location,
                source.get("employment_type", ""),
                f"{work_content} {requirements}",
            ),
            published=clean_text(row.get("updateDate") or row.get("publishDate") or ""),
            company=source.get("company", "百度"),
            location=location,
            employment_type=source.get("employment_type", ""),
            jd=compact_excerpt(work_content, 1800),
            requirements=compact_excerpt(requirements, 1000),
            job_id=job_id,
            source_type="baidu_campus",
            role_level=bool(job_id),
        )
        if item.title and source_accepts_item(source, item):
            items.append(item)
    return items


def source_accepts_item(source: dict, item: JobItem) -> bool:
    checks = [
        ("require_location_any", item.location),
        ("require_title_any", item.title),
        ("require_any", item_search_text(item)),
    ]
    for field, value in checks:
        terms = source.get(field, [])
        if terms and not matching_terms(normalize_for_match(value), terms):
            return False
    if source.get("require_title_all") and not all(
        matching_terms(normalize_for_match(item.title), [term])
        for term in source["require_title_all"]
    ):
        return False
    return True


def parse_payload(source: dict, text: str) -> list[JobItem]:
    parsers = {
        "html": parse_html_items, "rss": parse_rss_items,
        "ashby": parse_ashby_items, "greenhouse": parse_greenhouse_items,
        "lever": parse_lever_items, "mycareersfuture": parse_mycareersfuture_items,
        "baidu_campus": parse_baidu_campus_items, "wechat_search": parse_wechat_search_items,
    }
    return [item for item in parsers[source.get("type", "html")](source, text)
            if source_accepts_item(source, item)]
