"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the local research tool."""

    environment: str = "development"
    log_level: str = "INFO"
    database_path: Path = Path(".data/xhs_report.db")
    browser_profile_path: Path = Path(".data/xhs-profile")
    reports_path: Path = Path("reports")
    debug_path: Path = Path(".debug")

    detail_delay_min_seconds: float = 1.5
    detail_delay_max_seconds: float = 3.0
    scroll_delay_seconds: float = 1.2
    stable_scroll_rounds: int = 4
    login_timeout_seconds: int = 300

    feishu_app_id: str | None = Field(default=None, validation_alias="FEISHU_APP_ID")
    feishu_app_secret: str | None = Field(default=None, validation_alias="FEISHU_APP_SECRET")
    feishu_bitable_app_token: str | None = Field(
        default=None, validation_alias="FEISHU_BITABLE_APP_TOKEN"
    )
    feishu_account_table_id: str | None = Field(
        default=None, validation_alias="FEISHU_ACCOUNT_TABLE_ID"
    )
    feishu_note_table_id: str | None = Field(default=None, validation_alias="FEISHU_NOTE_TABLE_ID")
    feishu_report_table_id: str | None = Field(
        default=None, validation_alias="FEISHU_REPORT_TABLE_ID"
    )
    feishu_run_table_id: str | None = Field(default=None, validation_alias="FEISHU_RUN_TABLE_ID")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="XHS_REPORT_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_limits(self) -> "Settings":
        if self.stable_scroll_rounds < 1:
            raise ValueError("stable_scroll_rounds must be at least 1")
        if self.detail_delay_min_seconds < 0:
            raise ValueError("detail_delay_min_seconds cannot be negative")
        if self.detail_delay_max_seconds < self.detail_delay_min_seconds:
            raise ValueError("detail delay maximum must be greater than or equal to minimum")
        return self

    def ensure_local_directories(self) -> None:
        """Create non-secret local runtime directories."""

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.browser_profile_path.mkdir(parents=True, exist_ok=True)
        self.reports_path.mkdir(parents=True, exist_ok=True)
        self.debug_path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
