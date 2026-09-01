from __future__ import annotations

from datetime import datetime
from typing import Protocol

from news_aggregator.domain.models import (
    ArticleCandidate,
    ArticlePage,
    ArticleSearch,
    FeedDefinition,
    FeedStatus,
    StorageUsage,
)


class ArticleRepository(Protocol):
    def initialize(self) -> None: ...

    def save_articles(self, articles: tuple[ArticleCandidate, ...]) -> int: ...

    def search_articles(self, search: ArticleSearch) -> ArticlePage: ...

    def feed_status(self, feed_id: str) -> FeedStatus | None: ...

    def all_feed_statuses(self) -> tuple[FeedStatus, ...]: ...

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
    ) -> None: ...

    def storage_usage(self) -> StorageUsage: ...


class FeedLoader(Protocol):
    def load(
        self,
        feed: FeedDefinition,
        *,
        fetched_at: datetime,
    ) -> tuple[ArticleCandidate, ...]: ...
