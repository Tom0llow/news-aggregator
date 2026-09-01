from __future__ import annotations

from datetime import UTC, datetime

import pytest

from news_aggregator.application.errors import FeedLoadError
from news_aggregator.domain.models import FeedDefinition, SourceDefinition
from news_aggregator.infrastructure.rss import (
    MAX_ENTRY_CATEGORIES,
    MAX_FEED_BYTES,
    MAX_FEED_ENTRIES,
    HttpFeedClient,
    RssParser,
    plain_text_from_html,
)
from news_aggregator.infrastructure.source_catalog import allowed_feed_urls, default_sources

NOW = datetime(2026, 8, 31, 0, tzinfo=UTC)


def _source(source_id: str) -> SourceDefinition:
    return next(source for source in default_sources() if source.id == source_id)


def _feed(source_id: str) -> FeedDefinition:
    return _source(source_id).feeds[0]


def test_default_catalog_contains_only_reviewed_source_policies() -> None:
    sources = default_sources()

    assert [source.name for source in sources] == [
        "Yahoo!ニュース",
        "GIGAZINE",
        "ITmedia",
        "Ledge.ai",
        "Publickey",
        "ASCII.jp",
    ]
    assert sum(source.enabled for source in sources) == 5
    assert len(_source("yahoo").feeds) == 9
    assert _source("yahoo").kind.value == "portal"
    assert _source("itmedia").feeds[0].summary_allowed is False
    assert _source("ledge_ai").feeds == ()
    assert _source("ledge_ai").disabled_reason == "利用許可未確認のため取得しません"
    assert _source("ascii").feeds[0].minimum_interval_seconds == 3_600
    urls = allowed_feed_urls(sources)
    assert len(urls) == 13
    assert all(url.startswith("https://") for url in urls)


def test_plain_text_removes_markup_script_style_and_images() -> None:
    value = "<p>概要 <strong>本文</strong><img src='x'></p><script>攻撃</script><style>秘密</style>"

    assert plain_text_from_html(value) == "概要 本文"
    assert plain_text_from_html("<p>" + "あ" * 3_000 + "</p>", limit=20) == "あ" * 20


def test_rss2_parses_yahoo_portal_without_changing_title() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><item>
      <title>AIの新サービス発表\uff08共同通信\uff09</title>
      <link>https://news.yahoo.co.jp/articles/abc?utm_source=rss</link>
      <description><![CDATA[<p>日本語の概要です。</p><img src="ignored.jpg">]]></description>
      <pubDate>Sun, 30 Aug 2026 23:30:00 +0000</pubDate>
      <category>テクノロジー</category>
      <enclosure url="https://example.com/image.jpg" />
    </item></channel></rss>""".encode()
    source = _source("yahoo")
    feed = source.feeds[5]

    articles = RssParser().parse(xml, feed=feed, source=source, fetched_at=NOW)

    assert len(articles) == 1
    article = articles[0]
    assert article.title == "AIの新サービス発表\uff08共同通信\uff09"
    assert article.publisher == "共同通信"
    assert article.source_kind.value == "portal"
    assert article.timestamp_kind.value == "portal_provided"
    assert article.category == "IT"
    assert article.summary == "日本語の概要です。"
    assert article.duplicate_key == "https://news.yahoo.co.jp/articles/abc"
    assert "image" not in article.summary


def test_atom_uses_summary_and_ignores_content_and_keeps_category_scheme() -> None:
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Pythonの新機能</title>
        <link rel="alternate" href="https://www.publickey1.jp/blog/26/python.html" />
        <summary type="html">安全な&lt;b&gt;概要&lt;/b&gt;</summary>
        <content type="html">保存してはいけない本文と画像&lt;img src='x'&gt;</content>
        <published>2026-08-31T08:00:00+09:00</published>
        <author><name>Publickey</name></author>
        <category term="クラウド" scheme="urn:topic" />
      </entry>
    </feed>""".encode()
    source = _source("publickey")

    articles = RssParser().parse(xml, feed=_feed("publickey"), source=source, fetched_at=NOW)

    assert len(articles) == 1
    article = articles[0]
    assert article.summary == "安全な 概要"
    assert "保存してはいけない" not in article.summary
    assert article.publisher == "Publickey"
    assert article.category == "クラウド"
    assert article.tags == ("クラウド [urn:topic]",)
    assert article.published_at == datetime(2026, 8, 30, 23, tzinfo=UTC)


def test_atom_does_not_treat_xhtml_content_entry_as_an_article() -> None:
    xml = """<feed xmlns="http://www.w3.org/2005/Atom">
      <content type="xhtml"><div xmlns="http://www.w3.org/1999/xhtml">
        <entry>
          <title>本文内の保存禁止タイトル</title>
          <link href="https://www.publickey1.jp/blog/26/content-entry.html" />
          <summary>本文内の保存禁止概要</summary>
        </entry>
      </div></content>
    </feed>""".encode()
    source = _source("publickey")

    articles = RssParser().parse(xml, feed=_feed("publickey"), source=source, fetched_at=NOW)

    assert articles == ()


def test_rss2_does_not_treat_nested_or_namespaced_items_as_articles() -> None:
    xml = """<rss version="2.0"
        xmlns:content="http://purl.org/rss/1.0/modules/content/"
        xmlns:xhtml="http://www.w3.org/1999/xhtml"
        xmlns:extension="urn:example:extension">
      <channel>
        <content:encoded><xhtml:item>
          <xhtml:title>本文内の保存禁止タイトル</xhtml:title>
          <xhtml:link>https://example.jp/nested-item</xhtml:link>
          <xhtml:description>本文内の保存禁止概要</xhtml:description>
        </xhtml:item></content:encoded>
        <extension:item>
          <extension:title>拡張要素の保存禁止タイトル</extension:title>
          <extension:link>https://example.jp/namespaced-item</extension:link>
          <extension:description>拡張要素の保存禁止概要</extension:description>
        </extension:item>
      </channel>
    </rss>""".encode()
    source = _source("gigazine")

    articles = RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW)

    assert articles == ()


def test_atom_prefers_published_over_earlier_updated_element() -> None:
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Pythonの日時ニュース</title>
      <link href="https://www.publickey1.jp/blog/26/date.html" />
      <updated>2026-08-31T09:00:00+09:00</updated>
      <published>2026-08-30T08:00:00+09:00</published>
    </entry></feed>""".encode()
    source = _source("publickey")

    article = RssParser().parse(xml, feed=_feed("publickey"), source=source, fetched_at=NOW)[0]

    assert article.published_at == datetime(2026, 8, 29, 23, tzinfo=UTC)


def test_atom_updated_without_published_has_unknown_publication_date() -> None:
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Pythonの更新ニュース</title>
      <link href="https://www.publickey1.jp/blog/26/updated.html" />
      <updated>2026-08-31T09:00:00+09:00</updated>
    </entry></feed>""".encode()
    source = _source("publickey")

    article = RssParser().parse(xml, feed=_feed("publickey"), source=source, fetched_at=NOW)[0]

    assert article.published_at is None


def test_publickey_does_not_fall_back_to_description_when_summary_is_missing() -> None:
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
      <title>Pythonの日本語ニュース</title>
      <link href="https://www.publickey1.jp/blog/26/no-summary.html" />
      <description>保存してはいけない説明</description>
    </entry></feed>""".encode()
    source = _source("publickey")

    article = RssParser().parse(xml, feed=_feed("publickey"), source=source, fetched_at=NOW)[0]

    assert article.summary == ""


def test_itmedia_keeps_title_but_uses_empty_summary() -> None:
    xml = """<rss version="2.0"><channel><item>
      <title>PR\uff1a日本語の配信タイトル</title>
      <link>https://www.itmedia.co.jp/news/articles/2608/31/news001.html</link>
      <description>本文のような説明を保存しない</description>
      <dc:creator xmlns:dc="http://purl.org/dc/elements/1.1/">ITmedia NEWS</dc:creator>
    </item></channel></rss>""".encode()
    source = _source("itmedia")

    article = RssParser().parse(xml, feed=_feed("itmedia"), source=source, fetched_at=NOW)[0]

    assert article.title == "PR\uff1a日本語の配信タイトル"
    assert article.summary == ""
    assert article.publisher == "ITmedia NEWS"


def test_itmedia_uses_unsaved_description_only_for_japanese_detection() -> None:
    xml = """<rss version="2.0"><channel><item>
      <title>PR: New AI Service 2026</title>
      <link>https://www.itmedia.co.jp/news/articles/2608/31/news002.html</link>
      <description>広告を含む日本語の配信説明</description>
    </item></channel></rss>""".encode()
    source = _source("itmedia")

    article = RssParser().parse(xml, feed=_feed("itmedia"), source=source, fetched_at=NOW)[0]

    assert article.title == "PR: New AI Service 2026"
    assert article.summary == ""


def test_rdf_and_unknown_date_are_supported() -> None:
    xml = """<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns="http://purl.org/rss/1.0/">
      <item><title>日本語の記事</title><link>https://example.jp/item</link>
      <description>概要</description><date>not-a-date</date></item>
    </rdf:RDF>""".encode()
    source = _source("gigazine")

    article = RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW)[0]

    assert article.published_at is None


def test_parser_skips_non_japanese_missing_title_and_unsafe_link() -> None:
    xml = """<rss version="2.0"><channel>
      <item><title>English title</title><link>https://example.com/1</link></item>
      <item><link>https://example.com/2</link><description>日本語</description></item>
      <item><title>日本語</title><link>javascript:alert(1)</link></item>
    </channel></rss>""".encode()
    source = _source("gigazine")

    assert RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW) == ()


def test_source_category_alone_does_not_make_an_english_article_japanese() -> None:
    xml = b'<rss version="2.0"><channel><item><title>English only</title>'
    xml += b"<link>https://news.yahoo.co.jp/articles/item</link></item></channel></rss>"
    source = _source("yahoo")

    assert RssParser().parse(xml, feed=source.feeds[0], source=source, fetched_at=NOW) == ()


def test_parser_rejects_malformed_xml_and_naive_fetch_time() -> None:
    source = _source("gigazine")
    parser = RssParser()
    with pytest.raises(FeedLoadError, match="XML"):
        parser.parse(b"<rss>", feed=_feed("gigazine"), source=source, fetched_at=NOW)
    with pytest.raises(ValueError, match="タイムゾーン"):
        parser.parse(b"<rss />", feed=_feed("gigazine"), source=source, fetched_at=datetime.now())


@pytest.mark.parametrize(
    "xml",
    [
        b"<html><item><title>not a feed</title></item></html>",
        b'<rss version="2.0"><item><title>missing channel</title></item></rss>',
        b"<rss><channel /></rss>",
        b'<rss version="0.91"><channel /></rss>',
        b'<rss xmlns="urn:not-rss2" version="2.0"><channel /></rss>',
        b'<rss xmlns:extension="urn:extension" version="2.0"><extension:channel /></rss>',
        b'<feed xmlns="urn:not-atom"></feed>',
        b"<feed></feed>",
    ],
)
def test_parser_rejects_unrecognized_xml_and_rss_without_channel(xml: bytes) -> None:
    source = _source("gigazine")

    with pytest.raises(FeedLoadError):
        RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW)


@pytest.mark.parametrize(
    "xml",
    [
        b'<rss version="2.0"><channel /></rss>',
        b'<feed xmlns="http://www.w3.org/2005/Atom" />',
        (
            b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            b'xmlns="http://purl.org/rss/1.0/" />'
        ),
    ],
)
def test_parser_accepts_recognized_empty_feeds(xml: bytes) -> None:
    source = _source("gigazine")

    assert RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW) == ()


@pytest.mark.parametrize(
    "declaration",
    [
        (
            b'<!DOCTYPE rss [<!ENTITY seed "1234567890">'
            b'<!ENTITY giant "&seed;&seed;&seed;&seed;&seed;&seed;&seed;&seed;">]>'
        ),
        b"<!DOCTYPE rss>",
    ],
)
def test_parser_rejects_doctype_and_entity_declarations(declaration: bytes) -> None:
    xml = declaration + (
        b'<rss version="2.0"><channel><item><title>&giant;</title></item></channel></rss>'
    )
    source = _source("gigazine")

    with pytest.raises(FeedLoadError, match=r"DOCTYPE.*ENTITY"):
        RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW)


def test_parser_accepts_declaration_text_inside_cdata_and_comments() -> None:
    xml = b"""<rss version="2.0"><channel><!-- <!ENTITY fake "value"> --><item>
      <title>\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\xe8\xa8\x98\xe4\xba\x8b</title>
      <link>https://example.jp/declaration-text</link>
      <description><![CDATA[<!DOCTYPE not-a-declaration> \xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e\xe6\xa6\x82\xe8\xa6\x81]]></description>
    </item></channel></rss>"""
    source = _source("gigazine")

    article = RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW)[0]

    assert article.summary == "日本語概要"


def test_parser_reports_malformed_declaration_like_text_as_invalid_xml() -> None:
    xml = b'< ! DoCtYpE rss><rss version="2.0"><channel /></rss>'
    source = _source("gigazine")

    with pytest.raises(FeedLoadError, match="XML"):
        RssParser().parse(xml, feed=_feed("gigazine"), source=source, fetched_at=NOW)


def test_parser_rejects_oversized_feed_entry_and_category_counts() -> None:
    source = _source("gigazine")
    parser = RssParser()

    with pytest.raises(FeedLoadError, match="許容サイズ"):
        parser.parse(
            b" " * (MAX_FEED_BYTES + 1),
            feed=_feed("gigazine"),
            source=source,
            fetched_at=NOW,
        )

    items = "".join("<item />" for _ in range(MAX_FEED_ENTRIES + 1))
    with pytest.raises(FeedLoadError, match="記事数"):
        parser.parse(
            f'<rss version="2.0"><channel>{items}</channel></rss>'.encode(),
            feed=_feed("gigazine"),
            source=source,
            fetched_at=NOW,
        )

    categories = "".join(
        f"<category>tag-{index}</category>" for index in range(MAX_ENTRY_CATEGORIES + 1)
    )
    category_feed = f"""<rss version="2.0"><channel><item><title>日本語記事</title>
      <link>https://example.jp/item</link>{categories}</item></channel></rss>""".encode()
    with pytest.raises(FeedLoadError, match="カテゴリ数"):
        parser.parse(category_feed, feed=_feed("gigazine"), source=source, fetched_at=NOW)


def test_yahoo_rejects_article_urls_outside_reviewed_host() -> None:
    xml = """<rss version="2.0"><channel><item>
      <title>日本語のポータル記事</title>
      <link>https://evil.example/articles/abc</link>
    </item></channel></rss>""".encode()
    source = _source("yahoo")

    with pytest.raises(FeedLoadError, match="Yahoo!記事URL"):
        RssParser().parse(xml, feed=source.feeds[0], source=source, fetched_at=NOW)


def test_http_client_rejects_non_allowlisted_url_and_bad_timeout() -> None:
    with pytest.raises(ValueError, match="timeout"):
        HttpFeedClient(allowed_urls=frozenset(), timeout_seconds=0)
    client = HttpFeedClient(allowed_urls=frozenset({"https://allowed.example/feed"}))
    with pytest.raises(FeedLoadError, match="許可リスト"):
        client.fetch("https://other.example/feed")
