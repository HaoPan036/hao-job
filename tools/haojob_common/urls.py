"""The one URL identity form used by discovery (radar) and record sync.

The output is also stored: the collector's SQLite seen-store and the
changedetection bridge state use it as a key. Changing any output for an
existing input invalidates those keys, so the golden tests must stay green.
"""

from __future__ import annotations

import re
import urllib.parse


TRACKING_KEYS = frozenset({"spm", "from", "source"})
UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"


def normalize_url_component(value: str, safe: str) -> str:
    # Only unreserved escapes are interchangeable with literal URI characters.
    # Keep encoded delimiters such as %2F and %3F encoded: they may be job IDs.
    def normalize_escape(match: re.Match) -> str:
        character = chr(int(match.group(0)[1:], 16))
        return character if character in UNRESERVED else match.group(0).upper()

    value = re.sub(r"%[0-9A-Fa-f]{2}", normalize_escape, value)
    return urllib.parse.quote(value, safe=safe + "%")


def canonical_url(url: str) -> str:
    """Return a comparison key for a job URL; never write it back over a user's link.

    Lowercases scheme and host, drops ``utm_*``, ``spm``, ``from`` and ``source``
    query parameters, removes a trailing path slash, decodes escaped unreserved
    characters, uppercases remaining escapes and percent-encodes other literal
    characters outside the kept delimiters. Literal and escaped parentheses
    therefore compare equal, while ``%2F`` stays distinct from ``/`` and ``+``
    stays distinct from ``%20`` and ``%2B``.
    """
    parsed = urllib.parse.urlsplit(url)
    # Preserve meaningful query order, repeated keys and encoded delimiters.
    # Do not round-trip through parse_qsl, which treats '+' as a space.
    filtered = []
    for part in parsed.query.split("&"):
        key = urllib.parse.unquote(part.partition("=")[0]).lower()
        if key.startswith("utm_") or key in TRACKING_KEYS:
            continue
        filtered.append(normalize_url_component(part, "/?:@!$'*+,;=-._~"))
    return urllib.parse.urlunsplit((
        parsed.scheme.lower(), parsed.netloc.lower(),
        normalize_url_component(parsed.path.rstrip("/"), "/:@!$&'*+,;=-._~"),
        "&".join(filtered), normalize_url_component(parsed.fragment, "/?:@!$&'*+,;=-._~")))
