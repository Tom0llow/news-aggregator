from __future__ import annotations

from news_aggregator.domain.models import (
    FeedDefinition,
    SourceDefinition,
    SourceKind,
    TimestampKind,
)

_YAHOO_CATEGORIES = (
    ("domestic", "国内"),
    ("world", "国際"),
    ("business", "経済"),
    ("entertainment", "エンタメ"),
    ("sports", "スポーツ"),
    ("it", "IT"),
    ("science", "科学"),
    ("life", "ライフ"),
    ("local", "地域"),
)


def default_sources() -> tuple[SourceDefinition, ...]:
    """Return the fixed, policy-reviewed source allow-list."""

    yahoo_feeds = tuple(
        FeedDefinition(
            id=f"yahoo_{slug}",
            source_id="yahoo",
            url=f"https://news.yahoo.co.jp/rss/categories/{slug}.xml",
            category=category,
        )
        for slug, category in _YAHOO_CATEGORIES
    )
    return (
        SourceDefinition(
            id="yahoo",
            name="Yahoo!ニュース",
            kind=SourceKind.PORTAL,
            timestamp_kind=TimestampKind.PORTAL_PROVIDED,
            enabled=True,
            disabled_reason=None,
            terms_note=(
                "公式カテゴリRSSのタイトル・概要・Yahoo!記事リンクだけを取得します。"
                "日時は記事の公開日時ではなくRSS上の提供日時です。"
            ),
            feeds=yahoo_feeds,
        ),
        SourceDefinition(
            id="gigazine",
            name="GIGAZINE",
            kind=SourceKind.DIRECT,
            timestamp_kind=TimestampKind.PUBLISHED,
            enabled=True,
            disabled_reason=None,
            terms_note="公式RSS 2.0を利用し、本文と画像は保存しません。",
            feeds=(
                FeedDefinition(
                    id="gigazine_main",
                    source_id="gigazine",
                    url="https://gigazine.net/news/rss_2.0/",
                ),
            ),
        ),
        SourceDefinition(
            id="itmedia",
            name="ITmedia",
            kind=SourceKind.DIRECT,
            timestamp_kind=TimestampKind.PUBLISHED,
            enabled=True,
            disabled_reason=None,
            terms_note=(
                "私的なローカルRSSリーダーとして公式RSSを利用します。配信タイトルを保持し、"
                "発信元を表示します。本文・画像・広告判定は取得しません。"
            ),
            feeds=(
                FeedDefinition(
                    id="itmedia_all",
                    source_id="itmedia",
                    url="https://rss.itmedia.co.jp/rss/2.0/itmedia_all.xml",
                    summary_allowed=False,
                ),
            ),
        ),
        SourceDefinition(
            id="ledge_ai",
            name="Ledge.ai",
            kind=SourceKind.DIRECT,
            timestamp_kind=TimestampKind.PUBLISHED,
            enabled=False,
            disabled_reason="利用許可未確認のため取得しません",
            terms_note=(
                "公式RSS/APIと収集許可を確認できていないため無効です。"
                "許可確認前はHTMLやサイトマップへアクセスしません。"
            ),
            feeds=(),
        ),
        SourceDefinition(
            id="publickey",
            name="Publickey",
            kind=SourceKind.DIRECT,
            timestamp_kind=TimestampKind.PUBLISHED,
            enabled=True,
            disabled_reason=None,
            terms_note="公式Atomのsummaryだけを概要に使い、contentは保存しません。",
            feeds=(
                FeedDefinition(
                    id="publickey_main",
                    source_id="publickey",
                    url="https://www.publickey1.jp/atom.xml",
                ),
            ),
        ),
        SourceDefinition(
            id="ascii",
            name="ASCII.jp",
            kind=SourceKind.DIRECT,
            timestamp_kind=TimestampKind.PUBLISHED,
            enabled=True,
            disabled_reason=None,
            terms_note=(
                "公式RSSを利用します。RSSのttl=60分を優先し、画像・enclosureは保存しません。"
            ),
            feeds=(
                FeedDefinition(
                    id="ascii_main",
                    source_id="ascii",
                    url="https://ascii.jp/rss.xml",
                    minimum_interval_seconds=3_600,
                ),
            ),
        ),
    )


def allowed_feed_urls(sources: tuple[SourceDefinition, ...]) -> frozenset[str]:
    return frozenset(
        feed.url for source in sources for feed in source.feeds if feed.url is not None
    )
