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
    "ignoreengage",
    "share_from_user_hidden",
    "share_red_id",
    "share_source",
    "source",
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
    match = re.search(r"/(?:explore|discovery/item)/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else stable_id("note", canonical_url(url))
