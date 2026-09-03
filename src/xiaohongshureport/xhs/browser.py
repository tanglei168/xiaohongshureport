"""Playwright persistent browser session without cookie extraction or stealth behavior."""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from loguru import logger
from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from xiaohongshureport.config import Settings
from xiaohongshureport.xhs import selectors

XHS_HOME_URL = "https://www.xiaohongshu.com/"


class LoginRequiredError(RuntimeError):
    """Raised when the isolated local browser profile has no valid session."""


class PlatformBlockedError(RuntimeError):
    """Raised when Xiaohongshu explicitly presents a risk or verification block."""


@contextmanager
def persistent_context(settings: Settings, *, headed: bool = True) -> Iterator[BrowserContext]:
    """Launch the project-owned Playwright profile and close it cleanly."""

    settings.ensure_local_directories()
    playwright: Playwright = sync_playwright().start()
    context: BrowserContext | None = None
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=settings.browser_profile_path,
            headless=not headed,
            viewport={"width": 1440, "height": 1000},
            locale="zh-CN",
        )
        yield context
    finally:
        if context is not None:
            context.close()
        playwright.stop()


def raise_if_platform_blocked(page: Page) -> None:
    """Stop on explicit risk/verification pages instead of attempting bypasses."""

    url = page.url.casefold()
    body = page.locator("body").inner_text(timeout=3_000)
    if "/website-login/error" in url or "安全限制" in body or "IP存在风险" in body:
        raise PlatformBlockedError(f"小红书明确阻止当前访问：{body[:160].strip()}")
    if "验证码" in body or "captcha" in url:
        raise PlatformBlockedError("小红书要求验证码，请在正常页面中人工处理后再运行")


def has_login_session(page: Page) -> bool:
    """Read the page's boolean login state without exporting any cookie values."""

    result = page.evaluate(
        "Boolean(window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user "
        "&& window.__INITIAL_STATE__.user.loggedIn)"
    )
    return result is True


def require_login(page: Page) -> None:
    raise_if_platform_blocked(page)
    if not has_login_session(page):
        raise LoginRequiredError("登录会话不存在或已失效，请执行：uv run xhs-report login")


def login(settings: Settings) -> None:
    """Open a headed browser and wait for the user to complete normal QR login."""

    with persistent_context(settings, headed=True) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(XHS_HOME_URL, wait_until="domcontentloaded")
        raise_if_platform_blocked(page)
        if has_login_session(page):
            logger.success("本地 Playwright profile 已有有效登录会话")
            return
        logger.info("请在打开的 Chromium 窗口中完成小红书扫码登录")
        deadline = time.monotonic() + settings.login_timeout_seconds
        while time.monotonic() < deadline:
            raise_if_platform_blocked(page)
            if has_login_session(page):
                page.wait_for_timeout(1500)
                logger.success("登录成功，session 已保存在 {}", settings.browser_profile_path)
                return
            if page.is_closed():
                raise LoginRequiredError("登录完成前浏览器已关闭，请重新执行 login")
            page.wait_for_timeout(1000)
        raise LoginRequiredError("等待登录超时，请重新执行 login")


def page_height(page: Page) -> int:
    return int(
        page.evaluate(
            """selector => {
                const element = document.querySelector(selector);
                return element ? element.scrollHeight : document.documentElement.scrollHeight;
            }""",
            selectors.SCROLL_CONTAINER,
        )
    )


def scroll_to_bottom(page: Page) -> None:
    page.evaluate(
        """selector => {
            const element = document.querySelector(selector);
            if (element) element.scrollTo(0, element.scrollHeight);
            else window.scrollTo(0, document.documentElement.scrollHeight);
        }""",
        selectors.SCROLL_CONTAINER,
    )
