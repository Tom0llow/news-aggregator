from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from news_aggregator.domain.rules import MAX_CATEGORY_LENGTH


class SourceKind(StrEnum):
    """How an article link relates to its publisher."""

    DIRECT = "direct"
    PORTAL = "portal"


class TimestampKind(StrEnum):
    """The meaning of the timestamp supplied by a feed."""

    PUBLISHED = "published"
    PORTAL_PROVIDED = "portal_provided"


class ArticleSort(StrEnum):
    """Supported article list orderings."""

    LATEST = "latest"
    VIEWS = "views"


@dataclass(frozen=True, slots=True)
class FeedDefinition:
    id: str
    source_id: str
    url: str | None
    category: str | None = None
    minimum_interval_seconds: int = 0
    summary_allowed: bool = True


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    id: str
    name: str
    kind: SourceKind
    timestamp_kind: TimestampKind
    enabled: bool
    disabled_reason: str | None
    terms_note: str
    feeds: tuple[FeedDefinition, ...]


@dataclass(frozen=True, slots=True)
class ArticleCandidate:
    title: str
    summary: str
    url: str
    duplicate_key: str
    source_id: str
    source_name: str
    publisher: str
    source_kind: SourceKind
    published_at: datetime | None
    timestamp_kind: TimestampKind
    fetched_at: datetime
    category: str | None
    tags: tuple[str, ...]
    fetch_error: str | None = None


@dataclass(frozen=True, slots=True)
class Article:
    id: int
    title: str
    summary: str
    url: str
    duplicate_key: str
    source_id: str
    source_name: str
    publisher: str
    source_kind: SourceKind
    published_at: datetime | None
    timestamp_kind: TimestampKind
    fetched_at: datetime
    category: str | None
    tags: tuple[str, ...]
    fetch_error: str | None
    view_count: int = 0


@dataclass(frozen=True, slots=True)
class ArticleSearch:
    keywords: tuple[str, ...] = ()
    source_id: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    page: int = 1
    limit: int = 30
    category: str | None = None
    sort: ArticleSort = ArticleSort.LATEST

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page は1以上で指定してください")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit は1から100の範囲で指定してください")
        if self.date_from == date.min:
            raise ValueError("date_from は0001-01-01より後の日付を指定してください")
        if self.date_to == date.max:
            raise ValueError("date_to は9999-12-31より前の日付を指定してください")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from は date_to 以前にしてください")
        if self.category is not None:
            if not self.category.strip():
                raise ValueError("category は空にできません")
            if len(self.category) > MAX_CATEGORY_LENGTH:
                raise ValueError("category が長すぎます")
        if not isinstance(self.sort, ArticleSort):
            raise ValueError("sort は latest または views で指定してください")


@dataclass(frozen=True, slots=True)
class ArticlePage:
    articles: tuple[Article, ...]
    total: int
    page: int
    limit: int


@dataclass(frozen=True, slots=True)
class FeedStatus:
    feed_id: str
    source_id: str
    status: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    error: str | None
    articles_seen: int
    articles_inserted: int
    skipped_reason: str | None


@dataclass(frozen=True, slots=True)
class FeedFetchResult:
    feed_id: str
    source_id: str
    status: str
    articles_seen: int = 0
    articles_inserted: int = 0
    error: str | None = None
    skipped_reason: str | None = None


@dataclass(frozen=True, slots=True)
class FetchReport:
    started_at: datetime
    finished_at: datetime
    results: tuple[FeedFetchResult, ...]

    @property
    def has_errors(self) -> bool:
        return any(result.status == "error" for result in self.results)


@dataclass(frozen=True, slots=True)
class StorageUsage:
    total_bytes: int
    files: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class FeedState:
    id: str
    category: str | None
    status: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    error: str | None
    articles_seen: int
    articles_inserted: int
    skipped_reason: str | None


@dataclass(frozen=True, slots=True)
class SourceState:
    id: str
    name: str
    kind: SourceKind
    enabled: bool
    disabled_reason: str | None
    terms_note: str
    status: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    error: str | None
    feeds: tuple[FeedState, ...]
