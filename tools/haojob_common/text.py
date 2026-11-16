"""Text helpers whose behaviour is identical in every tool that uses them."""

from __future__ import annotations

import html
import re


def clean_text(value: str) -> str:
    """Unescape HTML entities and collapse whitespace."""
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def contains_job_id(text: str, job_id: str) -> bool:
    """Match a job ID as a whole token, so ``DEMO-1`` does not match ``DEMO-10``."""
    return re.search(r"(?<![A-Za-z0-9_-])" + re.escape(job_id) + r"(?![A-Za-z0-9_-])", text) is not None
