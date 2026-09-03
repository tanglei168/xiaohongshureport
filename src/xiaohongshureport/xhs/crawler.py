"""Rate-limited account crawling and keyword discovery workflows."""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote
from uuid import uuid4

from loguru import logger
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from xiaohongshureport.config import Settings
from xiaohongshureport.debug import save_debug_artifact
from xiaohongshureport.models import AccountKeywordRelation, CrawlRun, NoteCard
from xiaohongshureport.storage import Database
from xiaohongshureport.utils import iso_now
from xiaohongshureport.xhs.browser import (
    note_page_is_unavailable,
    page_height,
    persistent_context,
    raise_if_platform_blocked,
    require_login,
    scroll_to_bottom,
    wait_for_page_ready,
)
from xiaohongshureport.xhs.parsing import (
    ParseError,
    parse_account,
    parse_note_cards,
    parse_note_detail,
)


@dataclass
class CrawlSummary:
    run_id: str
    account_id: str | None
    accounts_found: int
    notes_found: int
    notes_completed: int


class XhsCrawler:
    """Single-browser, sequential crawler for pages visible to the logged-in user."""

    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    def crawl_account(
        self,
        profile_url: str,
        *,
        max_notes: int | None = None,
        all_notes: bool = False,
        headed: bool = True,
        resume: bool = False,
    ) -> CrawlSummary:
        limit = None if all_notes else (max_notes if max_notes is not None else 50)
        run = CrawlRun(run_id=str(uuid4()), mode="crawl-account", target=profile_url)
        self.database.save_crawl_run(run)
        account_id: str | None = None
        notes_completed = 0
        try:
            with persistent_context(self.settings, headed=headed) as context:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(profile_url, wait_until="domcontentloaded")
                wait_for_page_ready(page)
                page.wait_for_timeout(3000)
                require_login(page)
                try:
                    account = parse_account(page.content(), page.url)
                except ParseError:
                    save_debug_artifact(page, self.settings.debug_path, "account parser")
                    raise
                account_id = account.account_id
                self.database.upsert_account(account)
                cards = self._scroll_and_collect(
                    page,
                    lambda html: parse_note_cards(html, page.url, account_id=account.account_id),
                    limit=limit,
                    on_new=self._persist_card,
                    parser_name="account note-card parser",
                )

                detail_page = context.new_page()
                for index, card in enumerate(cards, start=1):
                    if resume and self.database.note_detail_is_complete(card.note.note_id):
                        notes_completed += 1
                        logger.info(
                            "[{}/{}] resume 跳过已完成笔记 {}", index, len(cards), card.note.note_id
                        )
                        continue
                    self._rate_limit()
                    try:
                        detail_page.goto(
                            card.navigation_url or card.note.note_url,
                            wait_until="domcontentloaded",
                        )
                        detail_page.wait_for_timeout(900)
                        raise_if_platform_blocked(detail_page)
                        if note_page_is_unavailable(detail_page):
                            logger.warning("笔记当前不可浏览，跳过：{}", card.note.note_url)
                            continue
                        note = parse_note_detail(
                            detail_page.content(),
                            detail_page.url,
                            fallback_account_id=account.account_id,
                            source_keyword=card.note.source_keyword,
                        )
                        note = note.model_copy(
                            update={
                                "note_id": card.note.note_id,
                                "account_id": account.account_id,
                                "note_url": card.note.note_url,
                                "source_url": card.note.note_url,
                            }
                        )
                    except (ParseError, PlaywrightTimeoutError):
                        save_debug_artifact(
                            detail_page, self.settings.debug_path, "note detail parser"
                        )
                        logger.exception("笔记详情采集失败：{}", card.note.note_url)
                        continue
                    self.database.upsert_note(note)
                    notes_completed += 1
                    logger.info("[{}/{}] 已保存笔记详情 {}", index, len(cards), note.note_id)

            run.status = "completed"
            run.accounts_found = 1
            run.notes_found = len(cards)
            run.notes_completed = notes_completed
            run.finished_at = iso_now()
            self.database.save_crawl_run(run)
            return CrawlSummary(run.run_id, account_id, 1, len(cards), notes_completed)
        except Exception as error:
            run.status = "failed"
            run.error = str(error)
            run.finished_at = iso_now()
            self.database.save_crawl_run(run)
            raise

    def discover(
        self,
        keyword: str,
        *,
        max_notes: int | None = 100,
        headed: bool = True,
    ) -> tuple[CrawlSummary, list[AccountKeywordRelation]]:
        keyword = keyword.strip()
        if not keyword:
            raise ValueError("keyword cannot be empty")
        search_url = (
            "https://www.xiaohongshu.com/search_result?keyword="
            f"{quote(keyword)}&source=web_search_result_notes"
        )
        run = CrawlRun(run_id=str(uuid4()), mode="discover", target=keyword)
        self.database.save_crawl_run(run)
        try:
            with persistent_context(self.settings, headed=headed) as context:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(search_url, wait_until="domcontentloaded")
                wait_for_page_ready(page)
                page.wait_for_timeout(3000)
                require_login(page)
                cards = self._scroll_and_collect(
                    page,
                    lambda html: parse_note_cards(html, page.url, source_keyword=keyword),
                    limit=max_notes,
                    on_new=lambda card: self._persist_discovery_card(card, keyword, page.url),
                    parser_name="search note-card parser",
                )
                detail_page = context.new_page()
                notes_completed = 0
                for index, card in enumerate(cards, start=1):
                    if card.account is None:
                        continue
                    if self.database.note_detail_is_complete(card.note.note_id):
                        notes_completed += 1
                        continue
                    self._rate_limit()
                    try:
                        detail_page.goto(
                            card.navigation_url or card.note.note_url,
                            wait_until="domcontentloaded",
                        )
                        detail_page.wait_for_timeout(900)
                        raise_if_platform_blocked(detail_page)
                        if note_page_is_unavailable(detail_page):
                            logger.warning("搜索笔记当前不可浏览，跳过：{}", card.note.note_url)
                            continue
                        note = parse_note_detail(
                            detail_page.content(),
                            detail_page.url,
                            fallback_account_id=card.note.account_id,
                            source_keyword=keyword,
                        )
                        note = note.model_copy(
                            update={
                                "note_id": card.note.note_id,
                                "account_id": card.note.account_id,
                                "note_url": card.note.note_url,
                                "source_url": card.note.note_url,
                            }
                        )
                    except (ParseError, PlaywrightTimeoutError):
                        save_debug_artifact(
                            detail_page, self.settings.debug_path, "discover note detail parser"
                        )
                        logger.exception("搜索笔记详情采集失败：{}", card.note.note_url)
                        continue
                    self.database.upsert_note(note)
                    self.database.attach_note_keyword(note.note_id, keyword, search_url)
                    notes_completed += 1
                    logger.info("[{}/{}] 已补全搜索笔记 {}", index, len(cards), note.note_id)
            relations = self.database.recompute_keyword_relations(keyword)
            run.status = "completed"
            run.accounts_found = len({card.note.account_id for card in cards})
            run.notes_found = len(cards)
            run.notes_completed = notes_completed
            run.finished_at = iso_now()
            self.database.save_crawl_run(run)
            summary = CrawlSummary(
                run.run_id,
                None,
                run.accounts_found,
                run.notes_found,
                run.notes_completed,
            )
            return summary, relations
        except Exception as error:
            run.status = "failed"
            run.error = str(error)
            run.finished_at = iso_now()
            self.database.save_crawl_run(run)
            raise

    def _scroll_and_collect(
        self,
        page: Page,
        parser: Callable[[str], list[NoteCard]],
        *,
        limit: int | None,
        on_new: Callable[[NoteCard], None],
        parser_name: str,
    ) -> list[NoteCard]:
        seen: dict[str, NoteCard] = {}
        stable_rounds = 0
        previous_height = page_height(page)
        while stable_rounds < self.settings.stable_scroll_rounds:
            try:
                parsed = parser(page.content())
            except ParseError:
                save_debug_artifact(page, self.settings.debug_path, parser_name)
                raise
            new_count = 0
            for card in parsed:
                if card.note.note_id in seen:
                    continue
                seen[card.note.note_id] = card
                on_new(card)
                new_count += 1
                if limit is not None and len(seen) >= limit:
                    return list(seen.values())[:limit]
            scroll_to_bottom(page)
            page.wait_for_timeout(int(self.settings.scroll_delay_seconds * 1000))
            current_height = page_height(page)
            if current_height == previous_height and new_count == 0:
                stable_rounds += 1
            else:
                stable_rounds = 0
            previous_height = current_height
            logger.debug(
                "滚动采集：notes={} new={} stable={}/{} height={}",
                len(seen),
                new_count,
                stable_rounds,
                self.settings.stable_scroll_rounds,
                current_height,
            )
        if not seen:
            save_debug_artifact(page, self.settings.debug_path, parser_name)
            raise ParseError(f"{parser_name}: no note links found")
        return list(seen.values())

    def _persist_card(self, card: NoteCard) -> None:
        if card.account:
            self.database.upsert_account(card.account)
        self.database.upsert_note(card.note)

    def _persist_discovery_card(self, card: NoteCard, keyword: str, source_url: str) -> None:
        if card.account is None:
            logger.warning("搜索卡片缺少作者，跳过：{}", card.note.note_url)
            return
        self.database.upsert_account(card.account)
        self.database.upsert_note(card.note)
        self.database.attach_note_keyword(card.note.note_id, keyword, source_url)

    def _rate_limit(self) -> None:
        delay = random.uniform(
            self.settings.detail_delay_min_seconds,
            self.settings.detail_delay_max_seconds,
        )
        logger.debug("详情页访问前等待 {:.2f} 秒", delay)
        time.sleep(delay)
