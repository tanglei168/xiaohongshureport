"""HTML parsers that return source-attributed facts and never invent missing data."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from xiaohongshureport.models import Account, Note, NoteCard
from xiaohongshureport.utils import (
    account_id_from_url,
    canonical_url,
    iso_now,
    note_id_from_url,
)
from xiaohongshureport.xhs import selectors


class ParseError(ValueError):
    """Raised when a page lacks the minimum stable identity needed for parsing."""


def parse_count(value: str | int | None) -> int | None:
    """Parse exact and Chinese ten-thousand formatted counts."""

    if value is None or isinstance(value, int):
        return value
    text = value.strip().replace(",", "").replace("+", "")
    if not text or text in {"-", "--"}:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*([万wW]?)", text)
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2):
        number *= 10_000
    return int(number)


def parse_time(value: str | None, *, now: datetime | None = None) -> str | None:
    """Parse common displayed timestamps into timezone-aware ISO 8601 strings."""

    if not value:
        return None
    text = value.strip().replace("发布于", "").strip()
    current = now or datetime.now().astimezone()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)

    if text == "昨天":
        return (current - timedelta(days=1)).replace(microsecond=0).isoformat()
    relative = re.fullmatch(r"(\d+)\s*(分钟|小时|天)前", text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        delta = {
            "分钟": timedelta(minutes=amount),
            "小时": timedelta(hours=amount),
            "天": timedelta(days=amount),
        }[unit]
        return (current - delta).replace(microsecond=0).isoformat()

    try:
        parsed_iso = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        parsed_iso = None
    if parsed_iso is not None:
        if parsed_iso.tzinfo is None:
            parsed_iso = parsed_iso.replace(tzinfo=current.tzinfo)
        return parsed_iso.isoformat()

    normalized = text.replace("年", "-").replace("月", "-").replace("日", "").replace(".", "-")
    displayed_date = re.match(r"(?:\d{4}-)?\d{1,2}-\d{1,2}(?:\s+\d{1,2}:\d{2})?", normalized)
    if displayed_date:
        normalized = displayed_date.group(0)
    formats = ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%m-%d %H:%M", "%m-%d")
    for fmt in formats:
        try:
            parsed = datetime.strptime(normalized, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            parsed = parsed.replace(year=current.year)
            if parsed.replace(tzinfo=current.tzinfo) > current + timedelta(days=1):
                parsed = parsed.replace(year=current.year - 1)
        return parsed.replace(tzinfo=current.tzinfo).isoformat()

    return None


def _first(soup: BeautifulSoup | Tag, candidates: tuple[str, ...]) -> Tag | None:
    for candidate in candidates:
        found = soup.select_one(candidate)
        if found:
            return found
    return None


def _value(element: Tag | None, attribute: str | None = None) -> str | None:
    if element is None:
        return None
    if attribute:
        raw = element.get(attribute)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    if element.name == "meta":
        raw = element.get("content")
        return raw.strip() if isinstance(raw, str) and raw.strip() else None
    text = element.get_text(" ", strip=True)
    return text or None


def parse_account(html: str, profile_url: str, source_keyword: str | None = None) -> Account:
    soup = BeautifulSoup(html, "lxml")
    normalized_url = canonical_url(profile_url)
    nickname = _value(_first(soup, selectors.ACCOUNT_NICKNAME))
    if nickname and " - 小红书" in nickname:
        nickname = nickname.split(" - 小红书", 1)[0]
    if not nickname:
        raise ParseError("account parser: nickname not found")

    stats_text = _value(_first(soup, selectors.ACCOUNT_STATS)) or ""
    xhs_match = re.search(r"小红书号[：:]?\s*([\w-]+)", soup.get_text(" ", strip=True))
    ip_match = re.search(r"IP属地[：:]?\s*([^\s]+)", soup.get_text(" ", strip=True))

    def stat(label: str) -> int | None:
        match = re.search(rf"([\d.,万wW]+)\s*{label}", stats_text)
        if not match:
            match = re.search(rf"{label}\s*([\d.,万wW]+)", stats_text)
        return parse_count(match.group(1)) if match else None

    avatar = _first(soup, selectors.ACCOUNT_AVATAR)
    avatar_url = _value(avatar, "src") or _value(avatar)
    now = iso_now()
    return Account(
        account_id=account_id_from_url(normalized_url),
        nickname=nickname,
        profile_url=normalized_url,
        source_url=normalized_url,
        xhs_number=xhs_match.group(1) if xhs_match else None,
        bio=_value(_first(soup, selectors.ACCOUNT_BIO)),
        ip_location=ip_match.group(1) if ip_match else None,
        following_count=stat("关注"),
        follower_count=stat("粉丝"),
        likes_collections_count=stat("获赞与收藏") or stat("获赞和收藏"),
        avatar_url=urljoin(normalized_url, avatar_url) if avatar_url else None,
        crawl_time=now,
        first_seen_at=now,
        last_seen_at=now,
        source_keyword=source_keyword,
    )


def parse_note_cards(
    html: str,
    page_url: str,
    *,
    account_id: str | None = None,
    source_keyword: str | None = None,
) -> list[NoteCard]:
    soup = BeautifulSoup(html, "lxml")
    cards: dict[str, NoteCard] = {}
    for link in soup.select(selectors.NOTE_LINK):
        href = link.get("href")
        if not isinstance(href, str):
            continue
        note_url = canonical_url(urljoin(page_url, href))
        note_id = note_id_from_url(note_url)
        container = link.find_parent(["article", "li", "section"]) or link.parent or link
        title_element = container.select_one(selectors.NOTE_CARD_TITLE)
        title = _value(title_element) or _value(link, "title")
        cover = container.select_one(selectors.NOTE_CARD_IMAGE)
        like_element = container.select_one(selectors.NOTE_CARD_LIKE)
        author_link = container.select_one(selectors.ACCOUNT_LINK)

        card_account: Account | None = None
        resolved_account_id = account_id
        if author_link and isinstance(author_link.get("href"), str):
            profile_url = canonical_url(urljoin(page_url, str(author_link.get("href"))))
            resolved_account_id = account_id_from_url(profile_url)
            card_account = Account(
                account_id=resolved_account_id,
                nickname=_value(author_link),
                profile_url=profile_url,
                source_url=page_url,
                source_keyword=source_keyword,
            )
        if not resolved_account_id:
            continue

        note = Note(
            note_id=note_id,
            account_id=resolved_account_id,
            title=title,
            note_url=note_url,
            source_url=page_url,
            cover_url=urljoin(page_url, str(cover.get("src")))
            if cover and cover.get("src")
            else None,
            note_type="video" if container.select_one(selectors.VIDEO) else "image",
            like_count=parse_count(_value(like_element)),
            source_keyword=source_keyword,
        )
        cards[note_id] = NoteCard(note=note, account=card_account)
    return list(cards.values())


def parse_note_detail(
    html: str,
    note_url: str,
    *,
    fallback_account_id: str | None = None,
    source_keyword: str | None = None,
) -> Note:
    soup = BeautifulSoup(html, "lxml")
    normalized_url = canonical_url(note_url)
    author = _first(soup, selectors.NOTE_AUTHOR)
    author_href = author.get("href") if author else None
    if isinstance(author_href, str):
        account_id = account_id_from_url(urljoin(normalized_url, author_href))
    else:
        account_id = fallback_account_id
    if not account_id:
        raise ParseError("note detail parser: account identity not found")

    title = _value(_first(soup, selectors.NOTE_TITLE))
    content = _value(_first(soup, selectors.NOTE_CONTENT))
    if title and " - 小红书" in title:
        title = title.split(" - 小红书", 1)[0]
    if not title and not content:
        raise ParseError("note detail parser: title and content both missing")

    publish_element = _first(soup, selectors.NOTE_PUBLISH_TIME)
    publish_raw = _value(publish_element, "datetime") or _value(publish_element)
    hashtags = []
    for item in soup.select(", ".join(selectors.NOTE_HASHTAG)):
        tag = _value(item)
        if tag:
            cleaned = tag.lstrip("#").strip()
            if cleaned and cleaned not in hashtags:
                hashtags.append(cleaned)
    if content:
        for tag in re.findall(r"#([^#\s]+)", content):
            if tag not in hashtags:
                hashtags.append(tag)

    cover = _first(soup, selectors.NOTE_COVER)
    cover_url = _value(cover, "src") or _value(cover)
    return Note(
        note_id=note_id_from_url(normalized_url),
        account_id=account_id,
        title=title,
        content=content,
        note_url=normalized_url,
        source_url=normalized_url,
        cover_url=urljoin(normalized_url, cover_url) if cover_url else None,
        note_type="video" if soup.select_one(selectors.VIDEO) else "image",
        publish_time=parse_time(publish_raw),
        like_count=parse_count(_value(_first(soup, selectors.NOTE_LIKE))),
        collect_count=parse_count(_value(_first(soup, selectors.NOTE_COLLECT))),
        comment_count=parse_count(_value(_first(soup, selectors.NOTE_COMMENT))),
        share_count=parse_count(_value(_first(soup, selectors.NOTE_SHARE))),
        hashtags=hashtags,
        source_keyword=source_keyword,
        detail_crawled_at=iso_now(),
    )
