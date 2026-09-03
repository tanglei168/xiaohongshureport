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


def test_search_card_keeps_navigation_token_out_of_persisted_urls() -> None:
    html = """
    <section data-note-id="note003">
      <a href="/explore/note003" style="display:none"></a>
      <a class="cover" href="/search_result/note003?xsec_token=test-only"></a>
      <a href="/user/profile/account003?xsec_token=profile-only">作者</a>
      <h3>标题</h3>
    </section>
    """

    card = parse_note_cards(
        html,
        "https://www.xiaohongshu.com/search_result?keyword=test",
        source_keyword="test",
    )[0]

    assert card.note.note_id == "note003"
    assert card.note.note_url == "https://www.xiaohongshu.com/explore/note003"
    assert card.account is not None
    assert card.account.profile_url == "https://www.xiaohongshu.com/user/profile/account003"
    assert card.navigation_url is not None
    assert "xsec_token=test-only" in card.navigation_url


def test_profile_card_uses_data_note_id_and_runtime_navigation_url() -> None:
    html = """
    <section data-note-id="note004">
      <a href="/explore/note004" style="display:none"></a>
      <a class="cover"
         href="/user/profile/account001/note004?xsec_token=test-only"></a>
      <h3>主页笔记</h3>
    </section>
    """

    card = parse_note_cards(
        html,
        "https://www.xiaohongshu.com/user/profile/account001",
        account_id="account001",
    )[0]

    assert card.note.note_id == "note004"
    assert card.note.note_url == "https://www.xiaohongshu.com/explore/note004"
    assert card.account is None
    assert card.navigation_url is not None
    assert "/user/profile/account001/note004" in card.navigation_url


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


def test_note_detail_keeps_known_card_account(fixture_html: callable) -> None:
    note = parse_note_detail(
        fixture_html("note_detail.html"),
        "https://www.xiaohongshu.com/explore/note001",
        fallback_account_id="known-account",
    )

    assert note.account_id == "known-account"
