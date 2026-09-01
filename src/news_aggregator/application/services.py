from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from news_aggregator.application.errors import FeedLoadError
from news_aggregator.application.ports import ArticleRepository, FeedLoader
from news_aggregator.domain.models import (
    ArticlePage,
    ArticleSearch,
    FeedDefinition,
    FeedFetchResult,
    FeedState,
    FetchReport,
    SourceDefinition,
    SourceState,
    StorageUsage,
)
from news_aggregator.domain.rules import ensure_aware_utc

MAX_STORED_ERROR_LENGTH = 500
LOGGER = logging.getLogger(__name__)


class FetchInProgressError(Exception):
    """A fetch cycle is already active in this process."""


class NewsApplication:
    def __init__(
        self,
        *,
        repository: ArticleRepository,
        feed_loader: FeedLoader,
        sources: tuple[SourceDefinition, ...],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._feed_loader = feed_loader
        self._sources = sources
        self._clock = clock or (lambda: datetime.now(UTC))
        self._fetch_lock = threading.Lock()

    @property
    def sources(self) -> tuple[SourceDefinition, ...]:
        return self._sources

    def fetch_all(self) -> FetchReport:
        if not self._fetch_lock.acquire(blocking=False):
            raise FetchInProgressError("ニュース取得はすでに実行中です")
        started_at = self._now()
        results: list[FeedFetchResult] = []
        try:
            for source in self._sources:
                if not source.enabled:
                    continue
                for feed in source.feeds:
                    results.append(self._fetch_feed(feed))
            return FetchReport(
                started_at=started_at,
                finished_at=self._now(),
                results=tuple(results),
            )
        finally:
            self._fetch_lock.release()

    def search(self, search: ArticleSearch) -> ArticlePage:
        return self._repository.search_articles(search)

    def storage_usage(self) -> StorageUsage:
        return self._repository.storage_usage()

    def source_states(self) -> tuple[SourceState, ...]:
        stored = {status.feed_id: status for status in self._repository.all_feed_statuses()}
        result: list[SourceState] = []
        for source in self._sources:
            feeds = tuple(
                FeedState(
                    id=feed.id,
                    category=feed.category,
                    status=stored[feed.id].status if feed.id in stored else "never",
                    last_attempt_at=(
                        stored[feed.id].last_attempt_at if feed.id in stored else None
                    ),
                    last_success_at=(
                        stored[feed.id].last_success_at if feed.id in stored else None
                    ),
                    error=stored[feed.id].error if feed.id in stored else None,
                    articles_seen=(stored[feed.id].articles_seen if feed.id in stored else 0),
                    articles_inserted=(
                        stored[feed.id].articles_inserted if feed.id in stored else 0
                    ),
                    skipped_reason=(stored[feed.id].skipped_reason if feed.id in stored else None),
                )
                for feed in source.feeds
            )
            result.append(_source_state(source, feeds))
        return tuple(result)

    def _fetch_feed(self, feed: FeedDefinition) -> FeedFetchResult:
        attempted_at = self._now()
        try:
            previous = self._repository.feed_status(feed.id)
            if (
                feed.minimum_interval_seconds
                and previous is not None
                and previous.last_success_at is not None
                and (attempted_at - previous.last_success_at).total_seconds()
                < feed.minimum_interval_seconds
            ):
                reason = f"配信元の最小間隔 {feed.minimum_interval_seconds // 60} 分を優先"
                self._repository.record_feed_status(
                    feed_id=feed.id,
                    source_id=feed.source_id,
                    status="skipped",
                    attempted_at=attempted_at,
                    succeeded_at=None,
                    error=None,
                    articles_seen=0,
                    articles_inserted=0,
                    skipped_reason=reason,
                )
                return FeedFetchResult(
                    feed_id=feed.id,
                    source_id=feed.source_id,
                    status="skipped",
                    skipped_reason=reason,
                )
            articles = self._feed_loader.load(feed, fetched_at=attempted_at)
            inserted = self._repository.save_articles(articles)
            self._repository.record_feed_status(
                feed_id=feed.id,
                source_id=feed.source_id,
                status="success",
                attempted_at=attempted_at,
                succeeded_at=attempted_at,
                error=None,
                articles_seen=len(articles),
                articles_inserted=inserted,
                skipped_reason=None,
            )
            return FeedFetchResult(
                feed_id=feed.id,
                source_id=feed.source_id,
                status="success",
                articles_seen=len(articles),
                articles_inserted=inserted,
            )
        except Exception as exc:
            error = _safe_error(exc)
            try:
                self._repository.record_feed_status(
                    feed_id=feed.id,
                    source_id=feed.source_id,
                    status="error",
                    attempted_at=attempted_at,
                    succeeded_at=None,
                    error=error,
                    articles_seen=0,
                    articles_inserted=0,
                    skipped_reason=None,
                )
            except Exception:
                LOGGER.exception("フィードのエラー状態を保存できません", extra={"feed_id": feed.id})
            return FeedFetchResult(
                feed_id=feed.id,
                source_id=feed.source_id,
                status="error",
                error=error,
            )

    def _now(self) -> datetime:
        return ensure_aware_utc(self._clock())


def _safe_error(exc: Exception) -> str:
    message = str(exc) if isinstance(exc, FeedLoadError) else "内部処理に失敗しました"
    return f"{type(exc).__name__}: {message}"[:MAX_STORED_ERROR_LENGTH]


def _source_state(source: SourceDefinition, feeds: tuple[FeedState, ...]) -> SourceState:
    if not source.enabled:
        status = "disabled"
        error = source.disabled_reason
    elif any(feed.status == "error" for feed in feeds):
        status = "error"
        error = " / ".join(feed.error for feed in feeds if feed.error) or "取得エラー"
    elif feeds and all(feed.status == "never" for feed in feeds):
        status = "never"
        error = None
    elif feeds and all(feed.status == "skipped" for feed in feeds):
        status = "skipped"
        error = None
    else:
        status = "success"
        error = None
    attempts = [feed.last_attempt_at for feed in feeds if feed.last_attempt_at]
    successes = [feed.last_success_at for feed in feeds if feed.last_success_at]
    return SourceState(
        id=source.id,
        name=source.name,
        kind=source.kind,
        enabled=source.enabled,
        disabled_reason=source.disabled_reason,
        terms_note=source.terms_note,
        status=status,
        last_attempt_at=max(attempts) if attempts else None,
        last_success_at=max(successes) if successes else None,
        error=error,
        feeds=feeds,
    )
