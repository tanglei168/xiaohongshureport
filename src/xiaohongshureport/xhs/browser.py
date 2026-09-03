"""Playwright persistent browser session without cookie extraction or stealth behavior."""

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger
from playwright.sync_api import BrowserContext, Error, Page, Playwright, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from xiaohongshureport.config import Settings
from xiaohongshureport.xhs import selectors

XHS_HOME_URL = "https://www.xiaohongshu.com/"
XHS_SESSION_CHECK_URL = "https://www.xiaohongshu.com/search_result?keyword=session-check"


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
        _restore_storage_state(context, settings.browser_storage_state_path)
        yield context
    finally:
        if context is not None:
            try:
                context.storage_state(path=settings.browser_storage_state_path)
            except (Error, OSError) as error:
                logger.warning("本地 browser storage state 无法保存：{}", type(error).__name__)
            finally:
                context.close()
        playwright.stop()


def _restore_storage_state(context: BrowserContext, path: Path) -> None:
    """Restore project-local browser state without logging or exporting its values."""

    if not path.exists():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        cookies = state.get("cookies", [])
        if cookies:
            context.add_cookies(cookies)
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as error:
        logger.warning("本地 browser storage state 无法恢复，将重新登录：{}", type(error).__name__)


def raise_if_platform_blocked(page: Page) -> None:
    """Stop on explicit risk/verification pages instead of attempting bypasses."""

    url = page.url.casefold()
    try:
        body = page.locator("body").inner_text(timeout=3_000)
    except (Error, PlaywrightTimeoutError):
        body = ""
    if "/website-login/error" in url or "安全限制" in body or "IP存在风险" in body:
        raise PlatformBlockedError(f"小红书明确阻止当前访问：{body[:160].strip()}")
    if any(marker in body for marker in ("请完成验证", "滑块验证", "安全验证")) or "captcha" in url:
        raise PlatformBlockedError("小红书要求验证码，请在正常页面中人工处理后再运行")


def note_page_is_unavailable(page: Page) -> bool:
    """Identify an explicit removed/unavailable note response without treating it as data."""

    if "/404" in page.url and "error_code=300031" in page.url:
        return True
    try:
        return "当前笔记暂时无法浏览" in page.locator("body").inner_text(timeout=3_000)
    except (Error, PlaywrightTimeoutError):
        return False


def has_login_session(page: Page) -> bool:
    """Read the page's boolean login state without exporting any cookie values."""

    try:
        login_is_visible = any(
            page.locator(marker).first.is_visible(timeout=500) for marker in selectors.LOGIN_MARKERS
        )
        if login_is_visible:
            return False
    except Error:
        return False
    try:
        result = page.evaluate(
            "Boolean(window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user "
            "&& window.__INITIAL_STATE__.user.loggedIn "
            "&& window.__INITIAL_STATE__.global "
            "&& window.__INITIAL_STATE__.global.hasWebSession)"
        )
    except Error:
        return False
    return result is True


def wait_for_page_ready(page: Page, timeout_seconds: float = 20) -> None:
    """Wait through client redirects until URL and DOM are stable for two checks."""

    deadline = time.monotonic() + timeout_seconds
    previous_url = ""
    stable_checks = 0
    while time.monotonic() < deadline:
        try:
            ready = page.evaluate(
                "document.readyState === 'interactive' || document.readyState === 'complete'"
            )
            current_url = page.url
        except Error:
            ready = False
            current_url = ""
        if ready and current_url == previous_url:
            stable_checks += 1
            if stable_checks >= 2:
                return
        else:
            stable_checks = 0
        previous_url = current_url
        page.wait_for_timeout(500)
    try:
        if page.evaluate(
            "document.readyState === 'interactive' || document.readyState === 'complete'"
        ):
            logger.debug("SPA URL 持续变化，但 DOM 已可用，继续后续页面检查")
            return
    except Error:
        pass
    raise PlaywrightTimeoutError("页面在超时时间内未完成导航")


def require_login(page: Page) -> None:
    raise_if_platform_blocked(page)
    if not has_login_session(page):
        raise LoginRequiredError("登录会话不存在或已失效，请执行：uv run xhs-report login")


def login(settings: Settings) -> None:
    """Open a headed browser and wait for the user to complete normal QR login."""

    with persistent_context(settings, headed=True) as context:
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(XHS_SESSION_CHECK_URL, wait_until="domcontentloaded")
        wait_for_page_ready(page)
        page.wait_for_timeout(3000)
        raise_if_platform_blocked(page)
        if has_login_session(page):
            logger.success("本地 Playwright profile 已有有效登录会话")
            return
        logger.info("请在打开的 Chromium 窗口中完成小红书扫码登录")
        deadline = time.monotonic() + settings.login_timeout_seconds
        while time.monotonic() < deadline:
            wait_for_page_ready(page)
            raise_if_platform_blocked(page)
            if has_login_session(page):
                page.wait_for_timeout(1500)
                logger.success(
                    "登录成功，session 已保存在 {} 和 {}",
                    settings.browser_profile_path,
                    settings.browser_storage_state_path,
                )
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
