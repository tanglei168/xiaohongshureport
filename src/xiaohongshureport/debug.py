"""Debug artifact capture for changing page structures."""

from datetime import UTC, datetime
from pathlib import Path

from loguru import logger
from playwright.sync_api import Page


def save_debug_artifact(page: Page, root: Path, parser_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S_%fZ")
    artifact_dir = root / timestamp
    artifact_dir.mkdir(parents=True, exist_ok=False)
    page.screenshot(path=artifact_dir / "screenshot.png", full_page=True)
    (artifact_dir / "page.html").write_text(page.content(), encoding="utf-8")
    (artifact_dir / "url.txt").write_text(page.url, encoding="utf-8")
    logger.error("{} failed for {}; debug artifact: {}", parser_name, page.url, artifact_dir)
    return artifact_dir
