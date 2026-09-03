"""Command-line entry point for the local account research workflow."""

import sys
from typing import Annotated

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from xiaohongshureport.config import Settings, get_settings
from xiaohongshureport.feishu import (
    FeishuClient,
    FeishuConfigurationError,
    sync_database,
)
from xiaohongshureport.reporting import generate_account_report
from xiaohongshureport.storage import Database
from xiaohongshureport.xhs.browser import LoginRequiredError, PlatformBlockedError
from xiaohongshureport.xhs.browser import login as browser_login
from xiaohongshureport.xhs.crawler import XhsCrawler

app = typer.Typer(no_args_is_help=True, help="小红书账号运营研究工具")
feishu_app = typer.Typer(no_args_is_help=True, help="飞书多维表格管理")
app.add_typer(feishu_app, name="feishu")
console = Console()


def _runtime() -> tuple[Settings, Database]:
    settings = get_settings()
    settings.ensure_local_directories()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    return settings, Database(settings.database_path)


@app.command()
def login() -> None:
    """Open headed Chromium and keep the QR login session in .data/xhs-profile/."""

    settings, _ = _runtime()
    try:
        browser_login(settings)
    except (LoginRequiredError, PlatformBlockedError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error


@app.command()
def discover(
    keyword: Annotated[str, typer.Option("--keyword", help="要研究的关键词")],
    max_notes: Annotated[
        int, typer.Option("--max-notes", min=1, help="最多收集的搜索结果笔记数")
    ] = 100,
    headed: Annotated[
        bool, typer.Option("--headed/--headless", help="使用有头或无头浏览器")
    ] = True,
) -> None:
    """Discover related accounts and notes, then print a deterministic ranking."""

    settings, database = _runtime()
    try:
        summary, relations = XhsCrawler(settings, database).discover(
            keyword, max_notes=max_notes, headed=headed
        )
    except (LoginRequiredError, PlatformBlockedError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    table = Table(title=f"“{keyword}”候选账号排行榜")
    for column in ("排名", "账号", "昵称", "相关笔记", "总互动", "平均互动", "时间跨度", "分数"):
        table.add_column(column)
    for rank, relation in enumerate(relations, start=1):
        account = database.get_account(relation.account_id)
        table.add_row(
            str(rank),
            relation.account_id,
            account.nickname if account and account.nickname else "缺失",
            str(relation.keyword_note_count),
            str(relation.total_engagement),
            f"{relation.average_engagement:.1f}",
            f"{relation.time_span_days} 天",
            f"{relation.score:.2f}",
        )
    console.print(table)
    console.print(
        f"任务 {summary.run_id} 完成：{summary.accounts_found} 个账号，{summary.notes_found} 篇笔记"
    )


@app.command("crawl-account")
def crawl_account(
    url: Annotated[str, typer.Option("--url", help="小红书账号主页 URL")],
    max_notes: Annotated[
        int | None, typer.Option("--max-notes", min=1, help="最多采集的笔记数")
    ] = None,
    all_notes: Annotated[
        bool, typer.Option("--all", help="持续滚动直到页面稳定，不限制笔记数")
    ] = False,
    headed: Annotated[
        bool, typer.Option("--headed/--headless", help="使用有头或无头浏览器")
    ] = True,
    resume: Annotated[bool, typer.Option("--resume", help="跳过已经完成详情采集的笔记")] = False,
) -> None:
    """Collect a profile's visible history and persist each note immediately."""

    if all_notes and max_notes is not None:
        raise typer.BadParameter("--all 与 --max-notes 不能同时使用")
    settings, database = _runtime()
    try:
        summary = XhsCrawler(settings, database).crawl_account(
            url,
            max_notes=max_notes,
            all_notes=all_notes,
            headed=headed,
            resume=resume,
        )
    except (LoginRequiredError, PlatformBlockedError) as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(
        f"任务 {summary.run_id} 完成：发现 {summary.notes_found} 篇，"
        f"完成详情 {summary.notes_completed} 篇，账号 ID={summary.account_id}"
    )


@app.command()
def report(
    account: Annotated[str, typer.Option("--account", help="稳定账号 ID")],
) -> None:
    """Generate Markdown and JSON fact reports from local SQLite facts."""

    settings, database = _runtime()
    try:
        markdown_path, json_path = generate_account_report(database, account, settings.reports_path)
    except ValueError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"已生成 {markdown_path} 和 {json_path}")
    if all(
        (
            settings.feishu_app_id,
            settings.feishu_app_secret,
            settings.feishu_bitable_app_token,
        )
    ):
        with FeishuClient(settings) as client:
            tables = client.initialize_tables()
            result = sync_database(database, client, tables)
        console.print(f"飞书同步完成：{result}")


@feishu_app.command("init")
def feishu_init() -> None:
    """Validate credentials, create/check tables and print resolved table IDs."""

    settings, _ = _runtime()
    try:
        with FeishuClient(settings) as client:
            tables = client.initialize_tables()
    except FeishuConfigurationError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print("飞书多维表格已就绪：")
    for key, value in tables.as_dict().items():
        console.print(f"{key}={value}")


@feishu_app.command("sync")
def feishu_sync() -> None:
    """Idempotently synchronize local accounts, notes, runs and reports."""

    settings, database = _runtime()
    try:
        with FeishuClient(settings) as client:
            tables = client.initialize_tables()
            result = sync_database(database, client, tables)
    except FeishuConfigurationError as error:
        console.print(f"[red]{error}[/red]")
        raise typer.Exit(1) from error
    console.print(f"飞书同步完成：{result}")


if __name__ == "__main__":
    app()
