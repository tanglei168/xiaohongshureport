from pathlib import Path

from xiaohongshureport.models import Account, CrawlRun, Note
from xiaohongshureport.storage import SCHEMA_VERSION, Database


def account() -> Account:
    return Account(
        account_id="account001",
        nickname="清梧的爸爸",
        profile_url="https://www.xiaohongshu.com/user/profile/account001",
        source_url="https://www.xiaohongshu.com/user/profile/account001",
        follower_count=12_000,
    )


def note() -> Note:
    return Note(
        note_id="note001",
        account_id="account001",
        title="第一次采集",
        note_url="https://www.xiaohongshu.com/explore/note001",
        source_url="https://www.xiaohongshu.com/user/profile/account001",
        like_count=1,
    )


def test_sqlite_migration_and_idempotent_upsert(tmp_path: Path) -> None:
    database = Database(tmp_path / "xhs.db")
    database.upsert_account(account())
    database.upsert_note(note())
    completed = note().model_copy(
        update={
            "title": "详情标题",
            "content": "详情正文",
            "like_count": 12_000,
            "hashtags": ["哇叽星球"],
            "detail_crawled_at": "2026-09-03T00:00:00+00:00",
        }
    )
    database.upsert_note(completed)
    database.upsert_note(note())

    saved = database.get_note("note001")
    assert database.schema_version() == SCHEMA_VERSION
    assert len(database.list_notes("account001")) == 1
    assert saved is not None
    assert saved.title == "详情标题"
    assert saved.content == "详情正文"
    assert saved.like_count == 12_000
    assert saved.hashtags == ["哇叽星球"]
    assert database.note_detail_is_complete("note001")


def test_keyword_relation_is_idempotent(tmp_path: Path) -> None:
    database = Database(tmp_path / "xhs.db")
    database.upsert_account(account())
    database.upsert_note(note())
    database.attach_note_keyword("note001", "哇叽星球", note().source_url)
    database.attach_note_keyword("note001", "哇叽星球", note().source_url)

    relations = database.recompute_keyword_relations("哇叽星球")

    assert len(relations) == 1
    assert relations[0].keyword_note_count == 1
    assert relations[0].total_engagement == 1


def test_crawl_run_upsert(tmp_path: Path) -> None:
    database = Database(tmp_path / "xhs.db")
    run = CrawlRun(run_id="run001", mode="discover", target="哇叽星球")
    database.save_crawl_run(run)
    database.save_crawl_run(run.model_copy(update={"status": "completed", "notes_found": 2}))

    saved = database.list_crawl_runs()
    assert len(saved) == 1
    assert saved[0].status == "completed"
    assert saved[0].notes_found == 2
