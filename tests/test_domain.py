from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from news_aggregator.domain.models import ArticleSearch
from news_aggregator.domain.rules import (
    clean_tags,
    contains_japanese,
    ensure_aware_utc,
    normalize_http_url,
    normalize_whitespace,
    truncate_text,
)


def test_contains_japanese_accepts_japanese_scripts() -> None:
    assert contains_japanese("ひらがな")
    assert contains_japanese("ニュース")
    assert contains_japanese("生成AI")
    assert not contains_japanese("English only 123")


def test_url_normalization_preserves_display_and_is_conservative() -> None:
    raw = " HTTPS://Example.COM:443/path?b=2&utm_source=x&a=1&fbclid=z#section "

    display, duplicate_key = normalize_http_url(raw)

    assert display == raw.strip()
    assert duplicate_key == "https://example.com/path?b=2&a=1"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "ftp://example.com/article",
        "https:///missing-host",
        "https://user:secret@example.com/article",
        "https://example.com:bad/article",
    ],
)
def test_url_normalization_rejects_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError, match="URL"):
        normalize_http_url(url)


def test_text_and_tag_cleaning_is_bounded_and_stable() -> None:
    assert normalize_whitespace(" a\n  b ") == "a b"
    assert truncate_text("abcdef", 3) == "abc"
    assert clean_tags([" AI ", "ai", "", "開発"]) == ("AI", "開発")


def test_aware_utc_conversion_rejects_naive_values() -> None:
    value = datetime(2026, 8, 31, 9, tzinfo=UTC)
    assert ensure_aware_utc(value) == value
    with pytest.raises(ValueError, match="タイムゾーン"):
        ensure_aware_utc(datetime(2026, 8, 31, 9))


def test_article_search_validates_paging_and_date_order() -> None:
    assert ArticleSearch().limit == 30
    with pytest.raises(ValueError, match="page"):
        ArticleSearch(page=0)
    with pytest.raises(ValueError, match="limit"):
        ArticleSearch(limit=101)
    with pytest.raises(ValueError, match="date_from"):
        ArticleSearch(date_from=date.min)
    assert ArticleSearch(date_from=date.min + timedelta(days=1)).date_from == date(1, 1, 2)
    with pytest.raises(ValueError, match="date_to"):
        ArticleSearch(date_to=date.max)
    with pytest.raises(ValueError, match="date_from"):
        ArticleSearch(date_from=date(2026, 9, 1), date_to=date(2026, 8, 31))
