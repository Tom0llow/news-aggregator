from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from news_aggregator.application.errors import FeedLoadError
from news_aggregator.application.services import FetchInProgressError, NewsApplication
from news_aggregator.domain.models import (
    ArticleCandidate,
    FeedDefinition,
    FeedStatus,
    SourceDefinition,
    SourceKind,
    TimestampKind,
)
from news_aggregator.domain.rules import normalize_http_url
from news_aggregator.infrastructure.sqlite_repository import SqliteArticleRepository

NOW = datetime(2026, 8, 31, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class StubLoader:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.errors: dict[str, Exception] = {}

    def load(self, feed: FeedDefinition, *, fetched_at: datetime) -> tuple[ArticleCandidate, ...]:
        self.calls.append(feed.id)
        error = self.errors.get(feed.id)
        if error is not None:
            raise error
        return (_article(f"https://example.jp/{feed.id}", fetched_at=fetched_at),)


class BlockingLoader:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def load(self, feed: FeedDefinition, *, fetched_at: datetime) -> tuple[ArticleCandidate, ...]:
        del feed, fetched_at
        self.entered.set()
        if not self.release.wait(2):
            raise RuntimeError("test release timed out")
        return ()


class FailingStatusRepository(SqliteArticleRepository):
    def feed_status(self, feed_id: str) -> FeedStatus | None:
        if feed_id == "bad-status":
            raise sqlite3.DatabaseError("corrupt status")
        return super().feed_status(feed_id)


class FailingSkipStatusRepository(SqliteArticleRepository):
    fail_skipped = False

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
        if self.fail_skipped and status == "skipped":
            raise sqlite3.DatabaseError("cannot record skip")
        super().record_feed_status(
            feed_id=feed_id,
            source_id=source_id,
            status=status,
            attempted_at=attempted_at,
            succeeded_at=succeeded_at,
            error=error,
            articles_seen=articles_seen,
            articles_inserted=articles_inserted,
            skipped_reason=skipped_reason,
        )


def _article(url: str, *, fetched_at: datetime) -> ArticleCandidate:
    display, duplicate_key = normalize_http_url(url)
    return ArticleCandidate(
        title="日本語ニュース",
        summary="概要",
        url=display,
        duplicate_key=duplicate_key,
        source_id="direct",
        source_name="直接ソース",
        publisher="発行元",
        source_kind=SourceKind.DIRECT,
        published_at=fetched_at,
        timestamp_kind=TimestampKind.PUBLISHED,
        fetched_at=fetched_at,
        category="技術",
        tags=(),
    )


def _source(
    source_id: str,
    *feeds: FeedDefinition,
    enabled: bool = True,
) -> SourceDefinition:
    return SourceDefinition(
        id=source_id,
        name=f"{source_id}ソース",
        kind=SourceKind.DIRECT,
        timestamp_kind=TimestampKind.PUBLISHED,
        enabled=enabled,
        disabled_reason=None if enabled else "利用許可未確認",
        terms_note="テスト条件",
        feeds=tuple(feeds),
    )


def _repository(path: Path) -> SqliteArticleRepository:
    repository = SqliteArticleRepository(path)
    repository.initialize()
    return repository


def test_partial_failure_continues_and_disabled_source_is_never_loaded(tmp_path: Path) -> None:
    good = FeedDefinition(id="good", source_id="direct", url="https://example.jp/good")
    bad = FeedDefinition(id="bad", source_id="direct", url="https://example.jp/bad")
    disabled_feed = FeedDefinition(
        id="disabled_feed", source_id="disabled", url="https://example.jp/disabled"
    )
    sources = (_source("direct", bad, good), _source("disabled", disabled_feed, enabled=False))
    loader = StubLoader()
    loader.errors["bad"] = FeedLoadError("timeout")
    application = NewsApplication(
        repository=_repository(tmp_path / "news.db"),
        feed_loader=loader,
        sources=sources,
        clock=MutableClock(NOW),
    )

    report = application.fetch_all()

    assert loader.calls == ["bad", "good"]
    assert [result.status for result in report.results] == ["error", "success"]
    assert report.has_errors
    states = application.source_states()
    assert states[0].status == "error"
    assert states[0].last_success_at == NOW
    assert states[1].status == "disabled"
    assert states[1].error == "利用許可未確認"


def test_feed_status_read_failure_does_not_stop_later_feeds(tmp_path: Path) -> None:
    bad = FeedDefinition(id="bad-status", source_id="direct", url="https://example.jp/bad-status")
    good = FeedDefinition(id="good", source_id="direct", url="https://example.jp/good")
    repository = FailingStatusRepository(tmp_path / "news.db")
    repository.initialize()
    loader = StubLoader()
    application = NewsApplication(
        repository=repository,
        feed_loader=loader,
        sources=(_source("direct", bad, good),),
        clock=MutableClock(NOW),
    )

    report = application.fetch_all()

    assert [result.status for result in report.results] == ["error", "success"]
    assert loader.calls == ["good"]
    assert report.finished_at == NOW


def test_internal_errors_are_sanitized_in_status(tmp_path: Path) -> None:
    feed = FeedDefinition(id="secret", source_id="direct", url="https://example.jp/secret")
    loader = StubLoader()
    loader.errors["secret"] = RuntimeError("C:\\private\\secret-token")
    application = NewsApplication(
        repository=_repository(tmp_path / "news.db"),
        feed_loader=loader,
        sources=(_source("direct", feed),),
        clock=MutableClock(NOW),
    )

    result = application.fetch_all().results[0]

    assert result.status == "error"
    assert result.error == "RuntimeError: 内部処理に失敗しました"
    assert "secret-token" not in (application.source_states()[0].error or "")


def test_source_minimum_interval_skips_network_after_success(tmp_path: Path) -> None:
    feed = FeedDefinition(
        id="ascii",
        source_id="ascii",
        url="https://example.jp/ascii",
        minimum_interval_seconds=3_600,
    )
    loader = StubLoader()
    clock = MutableClock(NOW)
    application = NewsApplication(
        repository=_repository(tmp_path / "news.db"),
        feed_loader=loader,
        sources=(_source("ascii", feed),),
        clock=clock,
    )

    first = application.fetch_all()
    clock.now = NOW + timedelta(minutes=30)
    second = application.fetch_all()

    assert first.results[0].status == "success"
    assert second.results[0].status == "skipped"
    assert second.results[0].skipped_reason == "配信元の最小間隔 60 分を優先"
    assert loader.calls == ["ascii"]
    state = application.source_states()[0]
    assert state.status == "skipped"
    assert state.last_success_at == NOW


def test_skip_status_write_failure_returns_error_without_network_retry(tmp_path: Path) -> None:
    feed = FeedDefinition(
        id="ascii",
        source_id="ascii",
        url="https://example.jp/ascii",
        minimum_interval_seconds=3_600,
    )
    repository = FailingSkipStatusRepository(tmp_path / "news.db")
    repository.initialize()
    loader = StubLoader()
    clock = MutableClock(NOW)
    application = NewsApplication(
        repository=repository,
        feed_loader=loader,
        sources=(_source("ascii", feed),),
        clock=clock,
    )
    application.fetch_all()
    repository.fail_skipped = True
    clock.now = NOW + timedelta(minutes=30)

    result = application.fetch_all().results[0]

    assert result.status == "error"
    assert loader.calls == ["ascii"]
    status = repository.feed_status("ascii")
    assert status is not None
    assert status.status == "error"


def test_fetch_lock_rejects_concurrent_cycle(tmp_path: Path) -> None:
    feed = FeedDefinition(id="blocking", source_id="direct", url="https://example.jp/feed")
    loader = BlockingLoader()
    application = NewsApplication(
        repository=_repository(tmp_path / "news.db"),
        feed_loader=loader,
        sources=(_source("direct", feed),),
        clock=MutableClock(NOW),
    )
    worker = threading.Thread(target=application.fetch_all)
    worker.start()
    assert loader.entered.wait(1)

    with pytest.raises(FetchInProgressError):
        application.fetch_all()

    loader.release.set()
    worker.join(2)
    assert not worker.is_alive()


def test_storage_usage_is_exposed_by_application(tmp_path: Path) -> None:
    application = NewsApplication(
        repository=_repository(tmp_path / "news.db"),
        feed_loader=StubLoader(),
        sources=(),
        clock=MutableClock(NOW),
    )

    assert application.storage_usage().total_bytes > 0
    report = application.fetch_all()
    assert report.results == ()
    assert not report.has_errors
