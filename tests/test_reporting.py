import json
from pathlib import Path

from xiaohongshureport.models import Account, Note
from xiaohongshureport.reporting import generate_account_report
from xiaohongshureport.storage import Database


def test_generate_markdown_and_json_report(tmp_path: Path) -> None:
    database = Database(tmp_path / "xhs.db")
    account = Account(
        account_id="account001",
        nickname="清梧的爸爸",
        profile_url="https://www.xiaohongshu.com/user/profile/account001",
        source_url="https://www.xiaohongshu.com/user/profile/account001",
        follower_count=1_000,
    )
    database.upsert_account(account)
    for note in (
        Note(
            note_id="note001",
            account_id=account.account_id,
            title="RAZ 学习计划",
            content="宝藏小程序打卡",
            note_url="https://www.xiaohongshu.com/explore/note001",
            source_url=account.profile_url,
            publish_time="2025-01-02T08:00:00+08:00",
            like_count=100,
            collect_count=20,
            detail_crawled_at="2026-09-03T00:00:00+00:00",
        ),
        Note(
            note_id="note002",
            account_id=account.account_id,
            title="牛津树阅读",
            note_url="https://www.xiaohongshu.com/explore/note002",
            source_url=account.profile_url,
            publish_time="2025-02-02T08:00:00+08:00",
            like_count=200,
        ),
    ):
        database.upsert_note(note)
    database.attach_note_keyword("note001", "哇叽星球", account.profile_url)

    markdown_path, json_path = generate_account_report(
        database, account.account_id, tmp_path / "reports"
    )

    markdown = markdown_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert "## 账号概况" in markdown
    assert "## 数据完整性" in markdown
    assert "### 按周发文数量" in markdown
    assert "### 按互动率 Top 20" in markdown
    assert payload["overview"]["total_notes"] == 2
    assert "by_interaction_rate" in payload["top_notes"]
    assert (
        payload["first_observed_product_terms"][0]["statement_scope"]
        == "首次在当前采集数据中观察到"
    )
    assert payload["data_completeness"]["possibly_incomplete"] is True
    assert len(database.list_reports()) == 1
