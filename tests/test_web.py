from __future__ import annotations

import http.client
import json
import threading
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from news_aggregator.application.services import NewsApplication
from news_aggregator.domain.models import (
    ArticleCandidate,
    FeedDefinition,
    SourceKind,
    TimestampKind,
)
from news_aggregator.domain.rules import normalize_http_url
from news_aggregator.infrastructure.source_catalog import default_sources
from news_aggregator.infrastructure.sqlite_repository import SqliteArticleRepository
from news_aggregator.interfaces.web import (
    LocalNewsServer,
    create_local_server,
    is_loopback_host_header,
    validate_loopback_bind,
)

NOW = datetime(2026, 8, 31, 0, tzinfo=UTC)


class EmptyLoader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def load(self, feed: FeedDefinition, *, fetched_at: datetime) -> tuple[ArticleCandidate, ...]:
        del fetched_at
        self.calls.append(feed.id)
        return ()


def _article(url: str) -> ArticleCandidate:
    display, duplicate_key = normalize_http_url(url)
    return ArticleCandidate(
        title="日本語AIニュース",
        summary="東京で発表された概要",
        url=display,
        duplicate_key=duplicate_key,
        source_id="yahoo",
        source_name="Yahoo!ニュース",
        publisher="共同通信",
        source_kind=SourceKind.PORTAL,
        published_at=None,
        timestamp_kind=TimestampKind.PORTAL_PROVIDED,
        fetched_at=NOW,
        category="IT",
        tags=("生成AI",),
    )


def _start_server(tmp_path: Path) -> tuple[LocalNewsServer, threading.Thread, EmptyLoader]:
    repository = SqliteArticleRepository(tmp_path / "news.db")
    repository.initialize()
    repository.save_articles((_article("https://news.yahoo.co.jp/articles/test"),))
    loader = EmptyLoader()
    application = NewsApplication(
        repository=repository,
        feed_loader=loader,
        sources=default_sources(),
        clock=lambda: NOW,
    )
    server = create_local_server(host="127.0.0.1", port=0, application=application)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, loader


def _base_url(server: LocalNewsServer) -> str:
    return f"http://127.0.0.1:{int(server.server_address[1])}"


def _request(
    server: LocalNewsServer,
    path: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Message, bytes]:
    request = Request(_base_url(server) + path, data=body, headers=headers or {}, method=method)
    try:
        with urlopen(request, timeout=2) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def _stop_server(server: LocalNewsServer, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(2)


def test_static_assets_are_local_safe_and_have_content_headers(tmp_path: Path) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        status, headers, html = _request(server, "/")
        js_status, js_headers, javascript = _request(server, "/static/app.js")
        css_status, css_headers, _ = _request(server, "/static/style.css")
    finally:
        _stop_server(server, thread)

    assert status == js_status == css_status == 200
    assert headers.get_content_type() == "text/html"
    assert js_headers.get_content_type() == "text/javascript"
    assert css_headers.get_content_type() == "text/css"
    assert headers["Cache-Control"] == "no-cache"
    assert "default-src 'self'" in headers["Content-Security-Policy"]
    assert "ニュース集計".encode() in html
    assert "DB・WAL・SHM・journal".encode() in html
    assert b"localStorage" in javascript
    assert b"newsAggregator:v1:favorites" in javascript
    assert b"innerHTML" not in javascript
    assert b"setInterval(refreshView, REFRESH_INTERVAL_MS)" in javascript
    assert b'addEventListener("visibilitychange"' in javascript
    assert b"loadSources(), loadStorage()" in javascript
    assert b"search: { query:" in javascript
    assert b"q: state.search.query" in javascript
    assert b"commitSearchParameters();" in javascript
    assert javascript.count(b"requestGeneration !== articleRequestGeneration") == 2


def test_article_source_and_storage_json_endpoints(tmp_path: Path) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        article_status, article_headers, article_body = _request(
            server, "/api/articles?q=AI+%E6%9D%B1%E4%BA%AC&source=yahoo"
        )
        source_status, _, source_body = _request(server, "/api/sources")
        storage_status, _, storage_body = _request(server, "/api/storage")
    finally:
        _stop_server(server, thread)

    articles = json.loads(article_body)
    sources = json.loads(source_body)["sources"]
    storage = json.loads(storage_body)
    assert article_status == source_status == storage_status == 200
    assert article_headers.get_content_type() == "application/json"
    assert article_headers["Cache-Control"] == "no-store"
    assert articles["total"] == 1
    assert articles["articles"][0]["timestamp_kind"] == "portal_provided"
    assert articles["articles"][0]["published_at"] is None
    assert len(sources) == 6
    ledge = next(source for source in sources if source["id"] == "ledge_ai")
    assert ledge["status"] == "disabled"
    assert ledge["disabled_reason"] == "利用許可未確認のため取得しません"
    assert storage["total_bytes"] > 0


def test_manual_fetch_is_json_only_and_runs_all_enabled_feeds(tmp_path: Path) -> None:
    server, thread, loader = _start_server(tmp_path)
    try:
        status, _, body = _request(
            server,
            "/api/fetch",
            method="POST",
            body=b"{}",
            headers={"Content-Type": "application/json", "Origin": _base_url(server)},
        )
        bad_status, _, bad_body = _request(
            server,
            "/api/fetch",
            method="POST",
            body=b"not-json",
            headers={"Content-Type": "text/plain"},
        )
    finally:
        _stop_server(server, thread)

    payload = json.loads(body)
    assert status == 200
    assert not payload["has_errors"]
    assert len(payload["results"]) == 13
    assert len(loader.calls) == 13
    assert bad_status == 400
    assert "Content-Type" in json.loads(bad_body)["error"]


@pytest.mark.parametrize(
    "origin", [None, "http://127.0.0.1:1", "http://evil.example", "same-origin-with-slash"]
)
def test_manual_fetch_requires_exact_same_origin(tmp_path: Path, origin: str | None) -> None:
    server, thread, loader = _start_server(tmp_path)
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = (
            _base_url(server) + "/" if origin == "same-origin-with-slash" else origin
        )
    try:
        status, _, body = _request(
            server,
            "/api/fetch",
            method="POST",
            body=b"{}",
            headers=headers,
        )
    finally:
        _stop_server(server, thread)

    assert status == 400
    assert "オリジン" in json.loads(body)["error"]
    assert loader.calls == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/articles?q=a&q=b",
        "/api/articles?date_from=31-08-2026",
        "/api/articles?date_from=0001-01-01",
        "/api/articles?date_to=9999-12-31",
        "/api/articles?limit=101",
        "/api/articles?page=1000001",
        "/api/articles?source=unknown",
    ],
)
def test_invalid_article_queries_return_400(tmp_path: Path, path: str) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        status, _, body = _request(server, path)
    finally:
        _stop_server(server, thread)

    assert status == 400
    assert "error" in json.loads(body)


def test_unknown_route_and_host_header_are_rejected(tmp_path: Path) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        missing_status, _, _ = _request(server, "/missing")
        connection = http.client.HTTPConnection(
            "127.0.0.1", int(server.server_address[1]), timeout=2
        )
        connection.putrequest("GET", "/api/storage", skip_host=True)
        connection.putheader("Host", "evil.example")
        connection.endheaders()
        response = connection.getresponse()
        host_status = response.status
        host_body = response.read()
        connection.close()
    finally:
        _stop_server(server, thread)

    assert missing_status == 404
    assert host_status == 400
    assert "loopback" in json.loads(host_body)["error"]


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.1", "localhost", "::1"])
def test_non_ipv4_loopback_bind_is_rejected(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_bind(host)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("127.0.0.1", True),
        ("127.0.0.1:8765", True),
        ("localhost:8765", False),
        ("127.0.0.1:bad", False),
        ("[::1]:8765", False),
        ("", False),
    ],
)
def test_loopback_host_header_validation(value: str, expected: bool) -> None:
    assert is_loopback_host_header(value) is expected


def test_server_rejects_invalid_port(tmp_path: Path) -> None:
    repository = SqliteArticleRepository(tmp_path / "news.db")
    repository.initialize()
    application = NewsApplication(
        repository=repository,
        feed_loader=EmptyLoader(),
        sources=(),
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match="port"):
        create_local_server(host="127.0.0.1", port=70_000, application=application)


def test_server_waits_for_non_daemon_request_workers() -> None:
    assert LocalNewsServer.daemon_threads is False
    assert LocalNewsServer.block_on_close is True
