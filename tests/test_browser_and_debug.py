from pathlib import Path

import pytest

from xiaohongshureport.debug import save_debug_artifact
from xiaohongshureport.xhs.browser import (
    PlatformBlockedError,
    _restore_storage_state,
    has_login_session,
    note_page_is_unavailable,
    raise_if_platform_blocked,
)


class FakeLocator:
    def __init__(self, text: str) -> None:
        self.text = text

    def inner_text(self, timeout: int) -> str:
        assert timeout == 3_000
        return self.text

    @property
    def first(self) -> "FakeLocator":
        return self

    def is_visible(self, timeout: int) -> bool:
        assert timeout == 500
        return False


class FakePage:
    def __init__(self, *, url: str, body: str = "", logged_in: bool = False) -> None:
        self.url = url
        self.body = body
        self.logged_in = logged_in

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self.body)

    def evaluate(self, expression: str) -> bool:
        assert "loggedIn" in expression
        return self.logged_in

    def screenshot(self, *, path: Path, full_page: bool) -> None:
        assert full_page is True
        path.write_bytes(b"fake-png")

    def content(self) -> str:
        return "<html><body>changed DOM</body></html>"


class FakeContext:
    def __init__(self) -> None:
        self.cookies: list[dict[str, object]] = []

    def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.cookies.extend(cookies)


def test_login_state_uses_page_state_not_guest_cookie() -> None:
    assert has_login_session(FakePage(url="https://www.xiaohongshu.com/", logged_in=True))
    assert not has_login_session(FakePage(url="https://www.xiaohongshu.com/"))


def test_explicit_platform_block_is_not_bypassed() -> None:
    page = FakePage(
        url="https://www.xiaohongshu.com/website-login/error?error_code=300012",
        body="安全限制 IP存在风险",
    )

    with pytest.raises(PlatformBlockedError, match="明确阻止"):
        raise_if_platform_blocked(page)


def test_explicit_unavailable_note_is_not_parsed_as_content() -> None:
    page = FakePage(
        url="https://www.xiaohongshu.com/404?error_code=300031",
        body="当前笔记暂时无法浏览",
    )

    assert note_page_is_unavailable(page)


def test_project_local_storage_state_restores_cookies(tmp_path: Path) -> None:
    state_path = tmp_path / "storage-state.json"
    state_path.write_text(
        '{"cookies":[{"name":"session","value":"test-only","domain":".example.com",'
        '"path":"/","expires":-1,"httpOnly":true,"secure":true,"sameSite":"Lax"}],'
        '"origins":[]}',
        encoding="utf-8",
    )
    context = FakeContext()

    _restore_storage_state(context, state_path)  # type: ignore[arg-type]

    assert len(context.cookies) == 1
    assert context.cookies[0]["name"] == "session"


def test_debug_artifact_contains_required_files(tmp_path: Path) -> None:
    page = FakePage(url="https://www.xiaohongshu.com/explore/note001")

    artifact = save_debug_artifact(page, tmp_path, "note detail parser")

    assert (artifact / "screenshot.png").read_bytes() == b"fake-png"
    assert "changed DOM" in (artifact / "page.html").read_text(encoding="utf-8")
    assert (artifact / "url.txt").read_text(encoding="utf-8") == page.url
