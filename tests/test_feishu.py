from xiaohongshureport.feishu import account_payload, note_payload, run_payload
from xiaohongshureport.models import Account, CrawlRun, Note


def test_feishu_payloads_preserve_ids_and_nulls() -> None:
    account = Account(
        account_id="account001",
        nickname="清梧的爸爸",
        profile_url="https://www.xiaohongshu.com/user/profile/account001",
        source_url="https://www.xiaohongshu.com/user/profile/account001",
    )
    note = Note(
        note_id="note001",
        account_id=account.account_id,
        note_url="https://www.xiaohongshu.com/explore/note001",
        source_url=account.profile_url,
        hashtags=["哇叽星球"],
    )
    run = CrawlRun(run_id="run001", mode="discover", target="哇叽星球")

    account_fields = account_payload(account, [note], None)
    note_fields = note_payload(note, account.nickname)
    run_fields = run_payload(run)

    assert account_fields["账号ID"] == "account001"
    assert "粉丝数" not in account_fields
    assert note_fields["笔记ID"] == "note001"
    assert note_fields["标签"] == "哇叽星球"
    assert "点赞" not in note_fields
    assert run_fields["任务ID"] == "run001"
