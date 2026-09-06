from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

from news_aggregator.domain.models import (
    ArticleCandidate,
    ArticleSearch,
    ArticleSort,
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


def test_schema_v1_migration_preserves_articles_and_adds_view_indexes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v1.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                url TEXT NOT NULL,
                duplicate_key TEXT NOT NULL UNIQUE,
                source_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                publisher TEXT NOT NULL,
                source_kind TEXT NOT NULL,
                published_at TEXT,
                timestamp_kind TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                category TEXT,
                tags_json TEXT NOT NULL,
                fetch_error TEXT
            );
            INSERT INTO articles (
                title, summary, url, duplicate_key, source_id, source_name, publisher,
                source_kind, published_at, timestamp_kind, fetched_at, category,
                tags_json, fetch_error
            ) VALUES (
                '既存記事', '概要', 'https://example.jp/existing',
                'https://example.jp/existing', 'source', 'ソース', '発行元', 'direct',
                '2026-08-31T00:00:00Z', 'published', '2026-08-31T00:00:00Z',
                '技術', '["開発"]', NULL
            );
            PRAGMA user_version = 1;
            """
        )

    repository = _repository(path)

    page = repository.search_articles(ArticleSearch(category="技術"))
    with sqlite3.connect(path) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(articles)")}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(articles)")}
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2
    assert page.total == 1
    assert page.articles[0].title == "既存記事"
    assert page.articles[0].view_count == 0
    assert columns["view_count"][3] == 1
    assert columns["view_count"][4] == "0"
    assert {"idx_articles_category_latest", "idx_articles_category_views"} <= indexes


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


def test_category_filter_and_view_sort_use_stable_latest_tiebreakers(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    older = NOW - timedelta(days=1)
    repository.save_articles(
        (
            _article("https://example.jp/first", published_at=NOW, category="技術"),
            _article("https://example.jp/second", published_at=NOW, category="技術"),
            _article("https://example.jp/older", published_at=older, category="技術"),
            _article("https://example.jp/unknown", published_at=None, category="技術"),
            _article("https://example.jp/other", published_at=NOW, category="技術ニュース"),
        )
    )
    all_articles = repository.search_articles(ArticleSearch(limit=100)).articles
    ids = {article.url.rsplit("/", 1)[-1]: article.id for article in all_articles}
    for name in ("first", "second", "older", "older", "unknown"):
        repository.increment_article_view(ids[name])

    latest = repository.search_articles(ArticleSearch(category="技術"))
    by_views = repository.search_articles(ArticleSearch(category="技術", sort=ArticleSort.VIEWS))

    assert [article.url.rsplit("/", 1)[-1] for article in latest.articles] == [
        "second",
        "first",
        "older",
        "unknown",
    ]
    assert [article.url.rsplit("/", 1)[-1] for article in by_views.articles] == [
        "older",
        "second",
        "first",
        "unknown",
    ]
    assert [article.view_count for article in by_views.articles] == [2, 1, 1, 1]


def test_view_increment_is_atomic_and_missing_article_is_reported(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "news.db")
    repository.save_articles((_article("https://example.jp/article"),))
    article_id = repository.search_articles(ArticleSearch()).articles[0].id

    with ThreadPoolExecutor(max_workers=8) as executor:
        counts = tuple(executor.map(repository.increment_article_view, [article_id] * 24))

    article = repository.search_articles(ArticleSearch()).articles[0]
    assert sorted(count for count in counts if count is not None) == list(range(1, 25))
    assert article.view_count == 24
    assert repository.increment_article_view(article_id + 1_000) is None


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
