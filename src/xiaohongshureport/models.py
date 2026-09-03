"""Account-first domain models for collected facts and derived statistics."""

from pydantic import BaseModel, ConfigDict, Field

from xiaohongshureport.utils import iso_now


class FactModel(BaseModel):
    """Base for source-attributed collected facts."""

    model_config = ConfigDict(extra="forbid")


class Account(FactModel):
    account_id: str
    nickname: str | None = None
    profile_url: str
    source_url: str
    xhs_number: str | None = None
    bio: str | None = None
    ip_location: str | None = None
    following_count: int | None = None
    follower_count: int | None = None
    likes_collections_count: int | None = None
    avatar_url: str | None = None
    crawl_time: str = Field(default_factory=iso_now)
    first_seen_at: str = Field(default_factory=iso_now)
    last_seen_at: str = Field(default_factory=iso_now)
    source_keyword: str | None = None


class Note(FactModel):
    note_id: str
    account_id: str
    title: str | None = None
    content: str | None = None
    note_url: str
    source_url: str
    cover_url: str | None = None
    note_type: str | None = None
    publish_time: str | None = None
    like_count: int | None = None
    collect_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    hashtags: list[str] = Field(default_factory=list)
    crawl_time: str = Field(default_factory=iso_now)
    source_keyword: str | None = None
    detail_crawled_at: str | None = None

    @property
    def total_engagement(self) -> int:
        return sum(
            value or 0
            for value in (self.like_count, self.collect_count, self.comment_count, self.share_count)
        )


class NoteCard(FactModel):
    note: Note
    account: Account | None = None


class AccountKeywordRelation(FactModel):
    account_id: str
    keyword_id: str
    keyword: str
    keyword_note_count: int = 0
    total_engagement: int = 0
    average_engagement: float = 0.0
    max_engagement: int = 0
    earliest_publish_time: str | None = None
    latest_publish_time: str | None = None
    time_span_days: int = 0
    score: float = 0.0
    updated_at: str = Field(default_factory=iso_now)


class CrawlRun(FactModel):
    run_id: str
    mode: str
    target: str
    status: str = "running"
    started_at: str = Field(default_factory=iso_now)
    finished_at: str | None = None
    accounts_found: int = 0
    notes_found: int = 0
    notes_completed: int = 0
    error: str | None = None
