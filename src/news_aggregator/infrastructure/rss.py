from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from email.message import Message
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from io import BytesIO
from typing import IO, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)
from xml.etree import ElementTree
from xml.parsers import expat

from news_aggregator.application.errors import FeedLoadError
from news_aggregator.application.ports import FeedLoader
from news_aggregator.domain.models import ArticleCandidate, FeedDefinition, SourceDefinition
from news_aggregator.domain.rules import (
    MAX_CATEGORY_LENGTH,
    MAX_PUBLISHER_LENGTH,
    MAX_SUMMARY_LENGTH,
    MAX_TITLE_LENGTH,
    clean_tags,
    contains_japanese,
    ensure_aware_utc,
    normalize_http_url,
    truncate_text,
)

MAX_FEED_BYTES = 5 * 1024 * 1024
MAX_FEED_ENTRIES = 1_000
MAX_ENTRY_CATEGORIES = 100
USER_AGENT = "news-aggregator/0.1 (private local Japanese RSS reader)"
ATOM_NAMESPACE = "http://www.w3.org/2005/Atom"
RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RSS_NAMESPACE = "http://purl.org/rss/1.0/"

_YAHOO_PUBLISHER_SUFFIX = re.compile(r"[\uff08(]([^\uff08\uff09()]{1,80})[\uff09)]$")
_BLOCKED_HTML_ELEMENTS = frozenset(
    {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "object"}
)


class _ForbiddenXmlDeclaration(Exception):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in _BLOCKED_HTML_ELEMENTS:
            self._blocked_depth += 1
        elif self._blocked_depth == 0 and tag.lower() in {"br", "p", "div", "li"}:
            self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in _BLOCKED_HTML_ELEMENTS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCKED_HTML_ELEMENTS and self._blocked_depth:
            self._blocked_depth -= 1
        elif self._blocked_depth == 0 and tag.lower() in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._blocked_depth == 0:
            self.parts.append(data)


def plain_text_from_html(value: str, *, limit: int = MAX_SUMMARY_LENGTH) -> str:
    extractor = _TextExtractor()
    try:
        extractor.feed(value)
        extractor.close()
    except (ValueError, AssertionError):
        return ""
    return truncate_text(" ".join(extractor.parts), limit)


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> Request | None:
        del req, fp, code, msg, headers, newurl
        return None


class HttpFeedClient:
    def __init__(self, *, allowed_urls: frozenset[str], timeout_seconds: float = 15.0) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 120:
            raise ValueError("HTTP timeout は0より大きく120秒以下にしてください")
        self._allowed_urls = allowed_urls
        self._timeout_seconds = timeout_seconds
        self._opener = build_opener(_RejectRedirects())

    def fetch(self, url: str) -> bytes:
        if url not in self._allowed_urls:
            raise FeedLoadError("固定許可リスト外のフィードURLです")
        request = Request(
            url,
            headers={
                "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
                "Accept-Encoding": "identity",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                content = cast(bytes, response.read(MAX_FEED_BYTES + 1))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise FeedLoadError(f"フィード取得失敗 ({type(exc).__name__})") from exc
        if len(content) > MAX_FEED_BYTES:
            raise FeedLoadError("フィードが許容サイズを超えています")
        return content


class RssParser:
    def parse(
        self,
        xml_data: bytes,
        *,
        feed: FeedDefinition,
        source: SourceDefinition,
        fetched_at: datetime,
    ) -> tuple[ArticleCandidate, ...]:
        fetched_at = ensure_aware_utc(fetched_at)
        if len(xml_data) > MAX_FEED_BYTES:
            raise FeedLoadError("フィードが許容サイズを超えています")
        _reject_xml_declarations(xml_data)
        try:
            root = ElementTree.parse(BytesIO(xml_data)).getroot()
        except (ElementTree.ParseError, ValueError) as exc:
            raise FeedLoadError("フィードXMLを解析できません") from exc
        entries = _feed_entries(root)
        articles: list[ArticleCandidate] = []
        for entry in entries:
            article = self._parse_entry(entry, feed=feed, source=source, fetched_at=fetched_at)
            if article is not None:
                articles.append(article)
        return tuple(articles)

    def _parse_entry(
        self,
        entry: ElementTree.Element,
        *,
        feed: FeedDefinition,
        source: SourceDefinition,
        fetched_at: datetime,
    ) -> ArticleCandidate | None:
        title = plain_text_from_html(_child_text(entry, ("title",)), limit=MAX_TITLE_LENGTH)
        if not title:
            return None
        raw_url = _entry_link(entry)
        try:
            display_url, duplicate_key = normalize_http_url(raw_url)
        except ValueError:
            return None
        if source.id == "yahoo" and urlsplit(display_url).hostname != "news.yahoo.co.jp":
            raise FeedLoadError("Yahoo!記事URLのホストが契約外です")
        summary = ""
        language_summary = ""
        if feed.summary_allowed:
            summary_elements = (
                ("summary",) if source.id == "publickey" else ("summary", "description")
            )
            summary = plain_text_from_html(_child_text(entry, summary_elements))
            language_summary = summary
        elif source.id == "itmedia":
            language_summary = plain_text_from_html(_child_text(entry, ("description",)))
        category_values = _categories(entry)
        category = feed.category
        if category is None and category_values:
            category = truncate_text(category_values[0][0], MAX_CATEGORY_LENGTH) or None
        tag_values = [
            f"{term} [{scheme}]" if scheme else term for term, scheme in category_values if term
        ]
        tags = clean_tags(tag_values)
        language_text = " ".join((title, language_summary))
        if not contains_japanese(language_text):
            return None
        publisher = _publisher(entry, source)
        published_at = _parse_datetime(_child_text(entry, ("pubDate", "published", "date")))
        return ArticleCandidate(
            title=title,
            summary=summary,
            url=display_url,
            duplicate_key=duplicate_key,
            source_id=source.id,
            source_name=source.name,
            publisher=publisher,
            source_kind=source.kind,
            published_at=published_at,
            timestamp_kind=source.timestamp_kind,
            fetched_at=fetched_at,
            category=category,
            tags=tags,
        )


class RssFeedLoader(FeedLoader):
    def __init__(
        self,
        *,
        client: HttpFeedClient,
        parser: RssParser,
        sources: tuple[SourceDefinition, ...],
    ) -> None:
        self._client = client
        self._parser = parser
        self._sources = {source.id: source for source in sources}

    def load(
        self,
        feed: FeedDefinition,
        *,
        fetched_at: datetime,
    ) -> tuple[ArticleCandidate, ...]:
        if feed.url is None:
            raise FeedLoadError("無効なソースにはアクセスできません")
        source = self._sources.get(feed.source_id)
        if source is None or not source.enabled:
            raise FeedLoadError("未登録または無効なソースです")
        return self._parser.parse(
            self._client.fetch(feed.url),
            feed=feed,
            source=source,
            fetched_at=fetched_at,
        )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str | None:
    if not tag.startswith("{") or "}" not in tag:
        return None
    return tag[1:].partition("}")[0]


def _reject_xml_declarations(xml_data: bytes) -> None:
    parser = expat.ParserCreate()

    def reject_declaration(*_args: object) -> None:
        raise _ForbiddenXmlDeclaration

    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    try:
        parser.Parse(xml_data, True)
    except _ForbiddenXmlDeclaration as exc:
        raise FeedLoadError("DOCTYPEまたはENTITY宣言は使用できません") from exc
    except expat.ExpatError:
        # ElementTree below remains the authoritative parser for ordinary XML errors.
        pass


def _feed_entries(root: ElementTree.Element) -> tuple[ElementTree.Element, ...]:
    root_name = _local_name(root.tag)
    if root_name == "feed" and _namespace(root.tag) == ATOM_NAMESPACE:
        entry_tag = f"{{{ATOM_NAMESPACE}}}entry"
        container = root
    elif root_name == "rss" and _namespace(root.tag) is None and root.get("version") == "2.0":
        channel = next((element for element in root if element.tag == "channel"), None)
        if channel is None:
            raise FeedLoadError("RSSフィードにchannelがありません")
        entry_tag = "item"
        container = channel
    elif root_name == "RDF" and _namespace(root.tag) == RDF_NAMESPACE:
        entry_tag = f"{{{RSS_NAMESPACE}}}item"
        container = root
    else:
        raise FeedLoadError("対応していないXML形式です")

    entries = tuple(element for element in container if element.tag == entry_tag)
    if len(entries) > MAX_FEED_ENTRIES:
        raise FeedLoadError("フィードの記事数が上限を超えています")
    return entries


def _direct_children(
    element: ElementTree.Element, names: Iterable[str]
) -> Iterable[ElementTree.Element]:
    accepted = frozenset(names)
    return (child for child in element if _local_name(child.tag) in accepted)


def _child_text(element: ElementTree.Element, names: Iterable[str]) -> str:
    for name in names:
        for child in _direct_children(element, (name,)):
            value = " ".join(child.itertext()).strip()
            if value:
                return value
    return ""


def _entry_link(entry: ElementTree.Element) -> str:
    fallback = ""
    for link in _direct_children(entry, ("link",)):
        href = (link.get("href") or "").strip()
        if href:
            if (link.get("rel") or "alternate") == "alternate":
                return href
            fallback = fallback or href
        text = (link.text or "").strip()
        if text:
            return text
    return fallback


def _categories(entry: ElementTree.Element) -> list[tuple[str, str | None]]:
    categories: list[tuple[str, str | None]] = []
    for count, category in enumerate(_direct_children(entry, ("category", "subject")), start=1):
        if count > MAX_ENTRY_CATEGORIES:
            raise FeedLoadError("記事のカテゴリ数が上限を超えています")
        term = (category.get("term") or " ".join(category.itertext())).strip()
        scheme = (category.get("scheme") or "").strip() or None
        if term:
            categories.append((term, scheme))
    return categories


def _publisher(entry: ElementTree.Element, source: SourceDefinition) -> str:
    if source.id == "yahoo":
        title = _child_text(entry, ("title",))
        match = _YAHOO_PUBLISHER_SUFFIX.search(title)
        if match:
            return truncate_text(match.group(1), MAX_PUBLISHER_LENGTH)
    value = _child_text(entry, ("creator", "author", "source"))
    if not value:
        for author in _direct_children(entry, ("author",)):
            value = _child_text(author, ("name",))
            if value:
                break
    return truncate_text(value or source.name, MAX_PUBLISHER_LENGTH)


def _parse_datetime(value: str) -> datetime | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        parsed = parsedate_to_datetime(stripped)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
