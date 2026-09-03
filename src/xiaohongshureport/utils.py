"""Small deterministic helpers shared across modules."""

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = {
    "app_platform",
    "app_version",
    "author_share",
    "channel",
    "channel_type",
    "ignoreengage",
    "parent_page_channel_type",
    "share_from_user_hidden",
    "share_red_id",
    "share_source",
    "source",
    "xsec_source",
    "xsec_token",
    "xhsshare",
}


def iso_now() -> str:
    """Return the current UTC time as an ISO 8601 string."""

    return datetime.now(UTC).isoformat()


def canonical_url(url: str) -> str:
    """Normalize a URL while retaining query values that may identify content."""

    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.casefold() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), "")
    )


def stable_id(kind: str, value: str) -> str:
    digest = hashlib.sha256(f"{kind}:{value}".encode()).hexdigest()[:24]
    return f"{kind}_{digest}"


def account_id_from_url(url: str) -> str:
    match = re.search(r"/user/profile/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else stable_id("account", canonical_url(url))


def note_id_from_url(url: str) -> str:
    match = re.search(r"/(?:explore|discovery/item|search_result)/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else stable_id("note", canonical_url(url))


def public_note_url(url: str) -> str:
    """Return a stable public note URL without page-scoped access parameters."""

    parts = urlsplit(url.strip())
    match = re.search(r"/(?:explore|discovery/item|search_result)/([A-Za-z0-9_-]+)", parts.path)
    if not match:
        return canonical_url(url)
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), f"/explore/{match.group(1)}", "", "")
    )
