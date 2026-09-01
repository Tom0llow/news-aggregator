from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from news_aggregator.application.ports import ArticleRepository
from news_aggregator.domain.models import (
    Article,
    ArticleCandidate,
    ArticlePage,
    ArticleSearch,
    FeedStatus,
    SourceKind,
    StorageUsage,
    TimestampKind,
)
from news_aggregator.domain.rules import ensure_aware_utc

SCHEMA_VERSION = 1


def _jst_timezone() -> tzinfo:
    try:
        return ZoneInfo("Asia/Tokyo")
    except ZoneInfoNotFoundError:
        # Windows does not always ship the IANA database. Japan has used UTC+9
        # without daylight saving changes throughout the application's date range.
        return timezone(timedelta(hours=9), "JST")


JST = _jst_timezone()

_SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    url TEXT NOT NULL,
    duplicate_key TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    publisher TEXT NOT NULL,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('direct', 'portal')),
    published_at TEXT,
    timestamp_kind TEXT NOT NULL
        CHECK (timestamp_kind IN ('published', 'portal_provided')),
    fetched_at TEXT NOT NULL,
    category TEXT,
    tags_json TEXT NOT NULL,
    fetch_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);

CREATE TABLE IF NOT EXISTS feed_status (
    feed_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL,
    last_attempt_at TEXT,
    last_success_at TEXT,
    error TEXT,
    articles_seen INTEGER NOT NULL DEFAULT 0,
    articles_inserted INTEGER NOT NULL DEFAULT 0,
    skipped_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_feed_status_source ON feed_status(source_id);
"""


class UnsupportedSchemaError(Exception):
    """The database was created by a newer incompatible application."""


class SqliteArticleRepository(ArticleRepository):
    def __init__(self, path: Path) -> None:
        self._path = path.resolve()
        self._initialize_lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        with self._initialize_lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version > SCHEMA_VERSION:
                    raise UnsupportedSchemaError(
                        f"DB schema version {version} is newer than supported {SCHEMA_VERSION}"
                    )
                if version < 1:
                    connection.executescript(_SCHEMA_V1)
                    connection.execute("PRAGMA user_version = 1")
                connection.commit()

    def save_articles(self, articles: tuple[ArticleCandidate, ...]) -> int:
        if not articles:
            return 0
        rows = [
            (
                article.title,
                article.summary,
                article.url,
                article.duplicate_key,
                article.source_id,
                article.source_name,
                article.publisher,
                article.source_kind.value,
                _encode_datetime(article.published_at),
                article.timestamp_kind.value,
                _encode_datetime(article.fetched_at),
                article.category,
                json.dumps(article.tags, ensure_ascii=False, separators=(",", ":")),
                article.fetch_error,
            )
            for article in articles
        ]
        with self._connect() as connection:
            before = connection.total_changes
            connection.executemany(
                """
                INSERT INTO articles (
                    title, summary, url, duplicate_key, source_id, source_name, publisher,
                    source_kind, published_at, timestamp_kind, fetched_at, category,
                    tags_json, fetch_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(duplicate_key) DO NOTHING
                """,
                rows,
            )
            inserted = connection.total_changes - before
            connection.commit()
        return inserted

    def search_articles(self, search: ArticleSearch) -> ArticlePage:
        clauses: list[str] = []
        parameters: list[str | int] = []
        for keyword in search.keywords:
            pattern = f"%{_escape_like(keyword)}%"
            clauses.append(
                "("
                + " OR ".join(
                    f"{column} LIKE ? ESCAPE '\\'"
                    for column in (
                        "title",
                        "summary",
                        "COALESCE(category, '')",
                        "tags_json",
                    )
                )
                + ")"
            )
            parameters.extend((pattern, pattern, pattern, pattern))
        if search.source_id:
            clauses.append("source_id = ?")
            parameters.append(search.source_id)
        if search.date_from:
            clauses.append("published_at >= ?")
            parameters.append(_jst_day_start_utc(search.date_from).replace("+00:00", "Z"))
        if search.date_to:
            clauses.append("published_at < ?")
            next_day = search.date_to + timedelta(days=1)
            parameters.append(_jst_day_start_utc(next_day).replace("+00:00", "Z"))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            count_row = connection.execute(
                f"SELECT COUNT(*) FROM articles{where}", parameters
            ).fetchone()
            total = int(count_row[0])
            rows = connection.execute(
                f"""
                SELECT id, title, summary, url, duplicate_key, source_id, source_name,
                       publisher, source_kind, published_at, timestamp_kind, fetched_at,
                       category, tags_json, fetch_error
                FROM articles{where}
                ORDER BY published_at IS NULL, published_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (*parameters, search.limit, (search.page - 1) * search.limit),
            ).fetchall()
        return ArticlePage(
            articles=tuple(_row_to_article(row) for row in rows),
            total=total,
            page=search.page,
            limit=search.limit,
        )

    def feed_status(self, feed_id: str) -> FeedStatus | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT feed_id, source_id, status, last_attempt_at, last_success_at,
                       error, articles_seen, articles_inserted, skipped_reason
                FROM feed_status WHERE feed_id = ?
                """,
                (feed_id,),
            ).fetchone()
        return None if row is None else _row_to_feed_status(row)

    def all_feed_statuses(self) -> tuple[FeedStatus, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT feed_id, source_id, status, last_attempt_at, last_success_at,
                       error, articles_seen, articles_inserted, skipped_reason
                FROM feed_status ORDER BY source_id, feed_id
                """
            ).fetchall()
        return tuple(_row_to_feed_status(row) for row in rows)

    def record_feed_status(
        self,
        *,
        feed_id: str,
        source_id: str,
        status: str,
        attempted_at: datetime | None,
        succeeded_at: datetime | None,
        error: str | None,
        articles_seen: int,
        articles_inserted: int,
        skipped_reason: str | None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feed_status (
                    feed_id, source_id, status, last_attempt_at, last_success_at,
                    error, articles_seen, articles_inserted, skipped_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(feed_id) DO UPDATE SET
                    source_id = excluded.source_id,
                    status = excluded.status,
                    last_attempt_at = COALESCE(excluded.last_attempt_at, feed_status.last_attempt_at),
                    last_success_at = COALESCE(excluded.last_success_at, feed_status.last_success_at),
                    error = excluded.error,
                    articles_seen = excluded.articles_seen,
                    articles_inserted = excluded.articles_inserted,
                    skipped_reason = excluded.skipped_reason
                """,
                (
                    feed_id,
                    source_id,
                    status,
                    _encode_datetime(attempted_at),
                    _encode_datetime(succeeded_at),
                    error,
                    articles_seen,
                    articles_inserted,
                    skipped_reason,
                ),
            )
            connection.commit()

    def storage_usage(self) -> StorageUsage:
        candidates = (
            self._path,
            self._path.with_name(f"{self._path.name}-wal"),
            self._path.with_name(f"{self._path.name}-shm"),
            self._path.with_name(f"{self._path.name}-journal"),
        )
        files: list[tuple[str, int]] = []
        for candidate in candidates:
            try:
                size = candidate.stat().st_size
            except FileNotFoundError:
                continue
            files.append((candidate.name, size))
        return StorageUsage(total_bytes=sum(size for _, size in files), files=tuple(files))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _jst_day_start_utc(value: date) -> str:
    local_start = datetime.combine(value, time.min, tzinfo=JST)
    return local_start.astimezone(UTC).isoformat(timespec="seconds")


def _encode_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return ensure_aware_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _decode_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("stored datetime is not text")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _decode_tags(value: object) -> tuple[str, ...]:
    if not isinstance(value, str):
        raise ValueError("stored tags are not text")
    decoded: object = json.loads(value)
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise ValueError("stored tags are invalid")
    return tuple(item for item in decoded if isinstance(item, str))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("stored value is not text")
    return value


def _row_to_article(row: sqlite3.Row) -> Article:
    return Article(
        id=int(row["id"]),
        title=str(row["title"]),
        summary=str(row["summary"]),
        url=str(row["url"]),
        duplicate_key=str(row["duplicate_key"]),
        source_id=str(row["source_id"]),
        source_name=str(row["source_name"]),
        publisher=str(row["publisher"]),
        source_kind=SourceKind(str(row["source_kind"])),
        published_at=_decode_datetime(row["published_at"]),
        timestamp_kind=TimestampKind(str(row["timestamp_kind"])),
        fetched_at=_decode_datetime(row["fetched_at"]) or datetime.min.replace(tzinfo=UTC),
        category=_optional_str(row["category"]),
        tags=_decode_tags(row["tags_json"]),
        fetch_error=_optional_str(row["fetch_error"]),
    )


def _row_to_feed_status(row: sqlite3.Row) -> FeedStatus:
    return FeedStatus(
        feed_id=str(row["feed_id"]),
        source_id=str(row["source_id"]),
        status=str(row["status"]),
        last_attempt_at=_decode_datetime(row["last_attempt_at"]),
        last_success_at=_decode_datetime(row["last_success_at"]),
        error=_optional_str(row["error"]),
        articles_seen=int(row["articles_seen"]),
        articles_inserted=int(row["articles_inserted"]),
        skipped_reason=_optional_str(row["skipped_reason"]),
    )
