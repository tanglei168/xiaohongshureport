from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from xiaohongshureport.xhs.parsing import (
    parse_account,
    parse_count,
    parse_note_cards,
    parse_note_detail,
    parse_time,
)


@pytest.mark.parametrize(
    ("display", "expected"),
    [("1", 1), ("999", 999), ("1.2万", 12_000), ("3.1万", 31_000), ("--", None)],
)
def test_parse_count(display: str, expected: int | None) -> None:
    assert parse_count(display) == expected


def test_parse_time_to_iso8601() -> None:
    now = datetime(2026, 9, 3, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert parse_time("2025-06-18", now=now) == "2025-06-18T00:00:00+08:00"
    assert parse_time("08-23", now=now) == "2026-08-23T00:00:00+08:00"
    assert parse_time("2天前", now=now) == "2026-09-01T12:00:00+08:00"


def test_parse_account(fixture_html: callable) -> None:
    account = parse_account(
        fixture_html("account.html"),
        "https://www.xiaohongshu.com/user/profile/5b3de7ba6b58b70d04c0dd57",
        "哇叽星球",
    )

    assert account.account_id == "5b3de7ba6b58b70d04c0dd57"
    assert account.nickname == "清梧的爸爸"
    assert account.follower_count == 12_000
    assert account.likes_collections_count == 31_000
    assert account.source_url == account.profile_url


def test_parse_note_cards(fixture_html: callable) -> None:
    cards = parse_note_cards(
        fixture_html("note_cards.html"),
        "https://www.xiaohongshu.com/search_result?keyword=哇叽星球",
        source_keyword="哇叽星球",
    )

    assert [card.note.note_id for card in cards] == ["note001", "note002"]
    assert cards[0].note.account_id == "account001"
    assert cards[0].note.like_count == 12_000
    assert cards[0].account is not None
    assert cards[0].account.nickname == "清梧的爸爸"


def test_parse_note_detail(fixture_html: callable) -> None:
    note = parse_note_detail(
        fixture_html("note_detail.html"),
        "https://www.xiaohongshu.com/explore/note001",
        source_keyword="哇叽星球",
    )

    assert note.note_id == "note001"
    assert note.account_id == "account001"
    assert note.publish_time == "2025-06-18T08:30:00+08:00"
    assert note.like_count == 12_000
    assert note.collect_count == 31_000
    assert note.comment_count == 999
    assert note.share_count == 1
    assert note.hashtags == ["哇叽星球", "英语启蒙", "学习计划"]
    assert note.detail_crawled_at is not None
