"""Markdown digest rendering for collector runs."""
from __future__ import annotations

import urllib.parse

import radar
from collect_base import ScoredItem, require_http_url


def render_digest(rows: list[ScoredItem], errors: list[str], counts: dict[str, int],
                  health: dict, report_date: str, minimum_score: int) -> str:
    lines = [f"# {report_date} Job Radar", "",
             "Collected leads require official review. Retrieval scores are discovery signals.", "",
             f"- Raw listings: {sum(counts.values())}", f"- Visible unique leads: {len(rows)}",
             f"- Source/detail errors: {len(errors)}", "", "## Leads for review", ""]
    for index, row in enumerate(rows, 1):
        if row.retrieval_score < minimum_score:
            continue
        item = row.item
        title = radar.markdown_inline(item.title)
        url = urllib.parse.quote(item.url, safe=":/?&=#%+@;,$!~*'-._")
        # Even malformed source payloads remain inert text in the report.
        try:
            require_http_url(item.url)
            link = f"[Source posting]({url})"
        except ValueError:
            link = radar.markdown_inline(item.url)
        lines += [f"### {index}. {title}", "",
                  f"- {radar.markdown_inline(item.company)} | {radar.markdown_inline(item.location)} | {radar.markdown_inline(item.employment_type)}",
                  f"- {link}", f"- Source: {radar.markdown_inline(item.source)}; retrieval_score: {row.retrieval_score}",
                  "- Verification: PENDING; feasibility, capability and strategy: UNKNOWN",]
        if row.blocked_reasons:
            lines.append("- Review flags: " + radar.markdown_inline("; ".join(row.blocked_reasons)))
        if row.detail:
            lines += ["- JD: " + radar.markdown_inline(row.detail.jd),
                      "- Requirements: " + radar.markdown_inline(row.detail.requirements)]
        elif item.snippet:
            lines.append("- Listing excerpt: " + radar.markdown_inline(item.snippet))
        if item.expires:
            lines.append("- Reported deadline: " + radar.markdown_inline(item.expires))
        lines.append("")
    lines += ["## Source health", ""]
    for name, count in counts.items():
        record = health.get("sources", {}).get(name, {})
        lines.append(f"- {radar.markdown_inline(name)}: {count} listings; consecutive failure days: {record.get('consecutive_failures', 0)}")
    if errors:
        lines += ["", "## Collection errors", ""] + ["- " + radar.markdown_inline(error) for error in errors]
    lines += ["", "## Handoff", "", "Review official status, eligibility, personal evidence and materials in the existing JobDossier before using radar.py. No application queue or history was changed.", ""]
    return "\n".join(lines)
