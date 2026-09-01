from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from news_aggregator.domain.models import (
    ArticleCandidate,
    ArticleSearch,
    SourceKind,
    TimestampKind,
)
from news_aggregator.domain.rules import normalize_http_url
from news_aggregator.infrastructure.sqlite_repository import (
    SCHEMA_VERSION,
    SqliteArticleRepository,
    UnsupportedSchemaError,
)

NOW = datetime(2026, 8, 31, 0, tzinfo=UTC)


def _article(
    url: str,
    *,
    title: str = "生成AIのニュース",
    summary: str = "東京で新サービスを発表",
    source_id: str = "gigazine",
    published_at: datetime | None = NOW,
    category: str | None = "テクノロジー",
    tags: tuple[str, ...] = ("開発",),
) -> ArticleCandidate:
    display, duplicate_key = normalize_http_url(url)
    return ArticleCandidate(
        title=title,
        summary=summary,
        url=display,
        duplicate_key=duplicate_key,
        source_id=source_id,
        source_name="テストソース",
        publisher="発行元",
        source_kind=SourceKind.DIRECT,
        published_at=published_at,
        timestamp_kind=TimestampKind.PUBLISHED,
        fetched_at=NOW,
        category=category,
        tags=tags,
    )


def _repository(path: Path) -> SqliteArticleRepository:
    repository = SqliteArticleRepository(path)
    repository.initialize()
    return repository


def test_initialize_is_repeatable_and_sets_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "news.db"
    repository = _repository(path)
    repository.initialize()

    with sqlite3.connect(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert version == SCHEMA_VERSION
    assert repository.path == path.resolve()


def test_newer_schema_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "future.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(UnsupportedSchemaError, match="newer"):
        SqliteArticleRepository(path).initialize()


def test_duplicate_key_unique_constraint_prevents_second_url_variant(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    first = _article("https://example.jp/article?x=1&utm_source=a")
    second = _article("https://example.jp/article?x=1&utm_source=b", title="別タイトル")

    assert repository.save_articles((first,)) == 1
    assert repository.save_articles((second,)) == 0
    page = repository.search_articles(ArticleSearch())
    assert page.total == 1
    assert page.articles[0].title == first.title
    assert page.articles[0].tags == ("開発",)


def test_non_duplicate_integrity_errors_are_not_ignored(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    invalid = replace(_article("https://example.jp/invalid"), title=cast(str, None))

    with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
        repository.save_articles((invalid,))


def test_search_is_and_partial_across_four_fields_and_source(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    repository.save_articles(
        (
            _article("https://example.jp/1"),
            _article(
                "https://example.jp/2",
                title="クラウド技術",
                summary="大阪の話題",
                source_id="publickey",
                tags=("Python",),
            ),
            _article("https://example.jp/3", title="100%日本語", summary="記号検索"),
        )
    )

    matching = repository.search_articles(ArticleSearch(keywords=("AI", "東京")))
    tag_matching = repository.search_articles(ArticleSearch(keywords=("yth", "クラウ")))
    literal_wildcard = repository.search_articles(ArticleSearch(keywords=("100%日",)))
    source_filtered = repository.search_articles(ArticleSearch(source_id="publickey"))

    assert [article.url for article in matching.articles] == ["https://example.jp/1"]
    assert tag_matching.total == 1
    assert literal_wildcard.total == 1
    assert source_filtered.total == 1
    assert source_filtered.articles[0].source_id == "publickey"


def test_jst_date_filter_includes_local_day_and_excludes_unknown(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    repository.save_articles(
        (
            _article(
                "https://example.jp/start",
                published_at=datetime(2026, 8, 30, 15, tzinfo=UTC),
            ),
            _article(
                "https://example.jp/end",
                published_at=datetime(2026, 8, 31, 14, 59, 59, tzinfo=UTC),
            ),
            _article(
                "https://example.jp/next",
                published_at=datetime(2026, 8, 31, 15, tzinfo=UTC),
            ),
            _article("https://example.jp/unknown", published_at=None),
        )
    )

    unfiltered = repository.search_articles(ArticleSearch())
    filtered = repository.search_articles(
        ArticleSearch(date_from=date(2026, 8, 31), date_to=date(2026, 8, 31))
    )

    assert unfiltered.total == 4
    assert {article.url for article in filtered.articles} == {
        "https://example.jp/start",
        "https://example.jp/end",
    }
    assert unfiltered.articles[-1].published_at is None


def test_paging_uses_safe_limit_and_offset(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    repository.save_articles(tuple(_article(f"https://example.jp/{index}") for index in range(3)))

    first = repository.search_articles(ArticleSearch(page=1, limit=2))
    second = repository.search_articles(ArticleSearch(page=2, limit=2))

    assert first.total == 3
    assert len(first.articles) == 2
    assert len(second.articles) == 1


def test_feed_status_preserves_last_success_and_records_error_skip(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    repository.record_feed_status(
        feed_id="feed",
        source_id="source",
        status="success",
        attempted_at=NOW,
        succeeded_at=NOW,
        error=None,
        articles_seen=2,
        articles_inserted=1,
        skipped_reason=None,
    )
    repository.record_feed_status(
        feed_id="feed",
        source_id="source",
        status="error",
        attempted_at=NOW + timedelta(minutes=30),
        succeeded_at=None,
        error="timeout",
        articles_seen=0,
        articles_inserted=0,
        skipped_reason=None,
    )

    status = repository.feed_status("feed")
    assert status is not None
    assert status.status == "error"
    assert status.last_success_at == NOW
    assert status.last_attempt_at == NOW + timedelta(minutes=30)
    assert status.error == "timeout"
    assert repository.feed_status("missing") is None
    assert repository.all_feed_statuses() == (status,)


def test_storage_usage_reports_database_files(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    repository.save_articles((_article("https://example.jp/1"),))

    usage = repository.storage_usage()

    assert usage.total_bytes > 0
    assert any(name == "news.db" for name, _ in usage.files)
