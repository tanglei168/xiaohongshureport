"""Versioned SQLite persistence with account-first, idempotent upserts."""

import json
import math
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from xiaohongshureport.models import Account, AccountKeywordRelation, CrawlRun, Note
from xiaohongshureport.utils import iso_now, stable_id

SCHEMA_VERSION = 1

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    nickname TEXT,
    profile_url TEXT NOT NULL UNIQUE,
    source_url TEXT NOT NULL,
    xhs_number TEXT,
    bio TEXT,
    ip_location TEXT,
    following_count INTEGER,
    follower_count INTEGER,
    likes_collections_count INTEGER,
    avatar_url TEXT,
    crawl_time TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    source_keyword TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    note_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    title TEXT,
    content TEXT,
    note_url TEXT NOT NULL UNIQUE,
    source_url TEXT NOT NULL,
    cover_url TEXT,
    note_type TEXT,
    publish_time TEXT,
    like_count INTEGER,
    collect_count INTEGER,
    comment_count INTEGER,
    share_count INTEGER,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    crawl_time TEXT NOT NULL,
    source_keyword TEXT,
    detail_crawled_at TEXT
);

CREATE TABLE IF NOT EXISTS keywords (
    keyword_id TEXT PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS note_keywords (
    note_id TEXT NOT NULL REFERENCES notes(note_id) ON DELETE CASCADE,
    keyword_id TEXT NOT NULL REFERENCES keywords(keyword_id) ON DELETE CASCADE,
    source_url TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    PRIMARY KEY (note_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS account_keyword_relations (
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    keyword_id TEXT NOT NULL REFERENCES keywords(keyword_id) ON DELETE CASCADE,
    keyword_note_count INTEGER NOT NULL DEFAULT 0,
    total_engagement INTEGER NOT NULL DEFAULT 0,
    average_engagement REAL NOT NULL DEFAULT 0,
    max_engagement INTEGER NOT NULL DEFAULT 0,
    earliest_publish_time TEXT,
    latest_publish_time TEXT,
    time_span_days INTEGER NOT NULL DEFAULT 0,
    score REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    run_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    target TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    accounts_found INTEGER NOT NULL DEFAULT 0,
    notes_found INTEGER NOT NULL DEFAULT 0,
    notes_completed INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS reports (
    account_id TEXT PRIMARY KEY REFERENCES accounts(account_id) ON DELETE CASCADE,
    report_json TEXT NOT NULL,
    markdown TEXT NOT NULL,
    source_url TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_account_publish ON notes(account_id, publish_time);
CREATE INDEX IF NOT EXISTS idx_notes_detail_status ON notes(account_id, detail_crawled_at);
CREATE INDEX IF NOT EXISTS idx_note_keywords_keyword ON note_keywords(keyword_id, note_id);
CREATE INDEX IF NOT EXISTS idx_relations_keyword_score
    ON account_keyword_relations(keyword_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_runs_mode_started ON crawl_runs(mode, started_at DESC);
"""


class Database:
    """Small SQLite repository; each public write is transactionally committed."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            versions = {
                row["version"]
                for row in connection.execute("SELECT version FROM schema_migrations")
            }
            if 1 not in versions:
                connection.executescript(MIGRATION_1)
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (1, iso_now()),
                )

    def schema_version(self) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
        return int(row["version"] or 0)

    def upsert_account(self, account: Account) -> None:
        data = account.model_dump(mode="json")
        columns = list(data)
        placeholders = ", ".join("?" for _ in columns)
        updates = []
        for column in columns:
            if column == "account_id":
                continue
            if column == "first_seen_at":
                updates.append(
                    "first_seen_at = MIN(accounts.first_seen_at, excluded.first_seen_at)"
                )
            elif column == "last_seen_at":
                updates.append("last_seen_at = MAX(accounts.last_seen_at, excluded.last_seen_at)")
            elif column in {"profile_url", "source_url", "crawl_time"}:
                updates.append(f"{column} = excluded.{column}")
            else:
                updates.append(f"{column} = COALESCE(excluded.{column}, accounts.{column})")
        sql = (
            f"INSERT INTO accounts ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(account_id) DO UPDATE SET {', '.join(updates)}"
        )
        with self.connect() as connection:
            connection.execute(sql, tuple(data[column] for column in columns))

    def upsert_note(self, note: Note) -> None:
        data = note.model_dump(mode="json")
        data["hashtags_json"] = json.dumps(data.pop("hashtags"), ensure_ascii=False)
        columns = list(data)
        placeholders = ", ".join("?" for _ in columns)
        detail_fields = {
            "title",
            "content",
            "cover_url",
            "note_type",
            "publish_time",
            "like_count",
            "collect_count",
            "comment_count",
            "share_count",
        }
        updates = []
        for column in columns:
            if column == "note_id":
                continue
            if column == "hashtags_json":
                updates.append(
                    "hashtags_json = CASE WHEN excluded.hashtags_json = '[]' "
                    "THEN notes.hashtags_json ELSE excluded.hashtags_json END"
                )
            elif column in detail_fields:
                updates.append(
                    f"{column} = CASE WHEN excluded.detail_crawled_at IS NULL "
                    f"AND notes.detail_crawled_at IS NOT NULL THEN notes.{column} "
                    f"ELSE COALESCE(excluded.{column}, notes.{column}) END"
                )
            elif column in {"source_keyword", "detail_crawled_at"}:
                updates.append(f"{column} = COALESCE(excluded.{column}, notes.{column})")
            else:
                updates.append(f"{column} = excluded.{column}")
        sql = (
            f"INSERT INTO notes ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(note_id) DO UPDATE SET {', '.join(updates)}"
        )
        with self.connect() as connection:
            connection.execute(sql, tuple(data[column] for column in columns))

    def get_account(self, account_id: str) -> Account | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
        return Account.model_validate(dict(row)) if row else None

    def get_note(self, note_id: str) -> Note | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM notes WHERE note_id = ?", (note_id,)).fetchone()
        return self._note_from_row(row) if row else None

    def list_notes(self, account_id: str) -> list[Note]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM notes WHERE account_id = ? "
                "ORDER BY publish_time IS NULL, publish_time, note_id",
                (account_id,),
            ).fetchall()
        return [self._note_from_row(row) for row in rows]

    def list_accounts(self) -> list[Account]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM accounts ORDER BY account_id").fetchall()
        return [Account.model_validate(dict(row)) for row in rows]

    @staticmethod
    def _note_from_row(row: sqlite3.Row) -> Note:
        data = dict(row)
        data["hashtags"] = json.loads(data.pop("hashtags_json") or "[]")
        return Note.model_validate(
            {key: value for key, value in data.items() if key in Note.model_fields}
        )

    def note_detail_is_complete(self, note_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT detail_crawled_at FROM notes WHERE note_id = ?", (note_id,)
            ).fetchone()
        return bool(row and row["detail_crawled_at"])

    def attach_note_keyword(self, note_id: str, keyword: str, source_url: str) -> str:
        keyword = keyword.strip()
        keyword_id = stable_id("keyword", keyword.casefold())
        now = iso_now()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO keywords(keyword_id, keyword, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(keyword) DO UPDATE SET keyword = excluded.keyword",
                (keyword_id, keyword, now),
            )
            connection.execute(
                "INSERT INTO note_keywords(note_id, keyword_id, source_url, discovered_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT(note_id, keyword_id) DO UPDATE SET "
                "source_url = excluded.source_url",
                (note_id, keyword_id, source_url, now),
            )
        return keyword_id

    def recompute_keyword_relations(self, keyword: str) -> list[AccountKeywordRelation]:
        keyword_id = stable_id("keyword", keyword.strip().casefold())
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT n.account_id,
                       COUNT(*) AS keyword_note_count,
                       SUM(COALESCE(n.like_count, 0) + COALESCE(n.collect_count, 0) +
                           COALESCE(n.comment_count, 0) + COALESCE(n.share_count, 0))
                           AS total_engagement,
                       AVG(COALESCE(n.like_count, 0) + COALESCE(n.collect_count, 0) +
                           COALESCE(n.comment_count, 0) + COALESCE(n.share_count, 0))
                           AS average_engagement,
                       MAX(COALESCE(n.like_count, 0) + COALESCE(n.collect_count, 0) +
                           COALESCE(n.comment_count, 0) + COALESCE(n.share_count, 0))
                           AS max_engagement,
                       MIN(n.publish_time) AS earliest_publish_time,
                       MAX(n.publish_time) AS latest_publish_time
                FROM notes n
                JOIN note_keywords nk ON nk.note_id = n.note_id
                WHERE nk.keyword_id = ?
                GROUP BY n.account_id
                """,
                (keyword_id,),
            ).fetchall()

            relations = []
            for row in rows:
                earliest = row["earliest_publish_time"]
                latest = row["latest_publish_time"]
                span = 0
                if earliest and latest:
                    span = max(
                        0,
                        (datetime.fromisoformat(latest) - datetime.fromisoformat(earliest)).days,
                    )
                score = (
                    float(row["keyword_note_count"]) * 10
                    + math.log1p(row["total_engagement"] or 0)
                    + math.log1p(span)
                )
                relation = AccountKeywordRelation(
                    account_id=row["account_id"],
                    keyword_id=keyword_id,
                    keyword=keyword,
                    keyword_note_count=row["keyword_note_count"],
                    total_engagement=row["total_engagement"] or 0,
                    average_engagement=row["average_engagement"] or 0,
                    max_engagement=row["max_engagement"] or 0,
                    earliest_publish_time=earliest,
                    latest_publish_time=latest,
                    time_span_days=span,
                    score=score,
                )
                relation_data = relation.model_dump(exclude={"keyword"})
                columns = list(relation_data)
                connection.execute(
                    f"INSERT INTO account_keyword_relations ({', '.join(columns)}) "
                    f"VALUES ({', '.join('?' for _ in columns)}) "
                    "ON CONFLICT(account_id, keyword_id) DO UPDATE SET "
                    + ", ".join(
                        f"{column} = excluded.{column}"
                        for column in columns
                        if column not in {"account_id", "keyword_id"}
                    ),
                    tuple(relation_data[column] for column in columns),
                )
                relations.append(relation)
        return sorted(relations, key=lambda relation: relation.score, reverse=True)

    def keyword_notes(self, account_id: str) -> list[tuple[str, Note]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT k.keyword, n.* FROM notes n
                JOIN note_keywords nk ON nk.note_id = n.note_id
                JOIN keywords k ON k.keyword_id = nk.keyword_id
                WHERE n.account_id = ? ORDER BY n.publish_time IS NULL, n.publish_time
                """,
                (account_id,),
            ).fetchall()
        return [(row["keyword"], self._note_from_row(row)) for row in rows]

    def save_crawl_run(self, run: CrawlRun) -> None:
        data = run.model_dump(mode="json")
        columns = list(data)
        with self.connect() as connection:
            connection.execute(
                f"INSERT INTO crawl_runs ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)}) "
                "ON CONFLICT(run_id) DO UPDATE SET "
                + ", ".join(
                    f"{column} = excluded.{column}" for column in columns if column != "run_id"
                ),
                tuple(data[column] for column in columns),
            )

    def list_crawl_runs(self) -> list[CrawlRun]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM crawl_runs ORDER BY started_at DESC"
            ).fetchall()
        return [CrawlRun.model_validate(dict(row)) for row in rows]

    def save_report(
        self, account_id: str, report_data: dict[str, object], markdown: str, source_url: str
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO reports(account_id, report_json, markdown, source_url, generated_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(account_id) DO UPDATE SET "
                "report_json = excluded.report_json, markdown = excluded.markdown, "
                "source_url = excluded.source_url, generated_at = excluded.generated_at",
                (
                    account_id,
                    json.dumps(report_data, ensure_ascii=False, indent=2),
                    markdown,
                    source_url,
                    iso_now(),
                ),
            )

    def list_reports(self) -> list[dict[str, object]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM reports ORDER BY generated_at DESC").fetchall()
        return [dict(row) for row in rows]
