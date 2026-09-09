from __future__ import annotations

import http.client
import json
import logging
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
    search_form_start = html.index(b'<form id="search-form">')
    search_form_end = html.index(b"</form>", search_form_start)
    category_select = html.index(b'<select id="category" name="category">')
    assert search_form_start < category_select < search_form_end
    assert html.index("すべて".encode(), category_select) < html.index(
        b"</select>", category_select
    )
    assert b'id="article-sort"' in html
    assert b'id="category-selection"' not in html
    assert b'id="clear-category"' not in html
    assert b"localStorage" in javascript
    assert b"newsAggregator:v1:favorites" in javascript
    assert b"innerHTML" not in javascript
    assert b"setInterval(refreshView, REFRESH_INTERVAL_MS)" in javascript
    assert b'addEventListener("visibilitychange"' in javascript
    assert b"loadSources(), loadCategories(), loadStorage()" in javascript
    assert b'category: "", sort: "latest"' in javascript
    assert b"q: state.search.query" in javascript
    assert b"category: state.search.category" in javascript
    assert b'category: byId("category").value' in javascript
    assert b"sort: state.search.sort" in javascript
    assert b"commitSearchParameters();" in javascript
    assert b"async function loadCategories()" in javascript
    assert b'await requestJson("/api/categories")' in javascript
    assert b"const selectedCategory = select.value" in javascript
    assert b'element("option", "", category)' in javascript
    assert b"ensureCategoryOption(selectedCategory)" in javascript
    assert b"ensureCategoryOption(category)" in javascript
    assert b'byId("category").value = category' in javascript
    assert b'element("button", `category-button' in javascript
    assert b"article.tags.filter(Boolean)" in javascript
    assert b'element("span", "tag", value)' in javascript
    assert b"void recordArticleView(article, details, timeKind)" in javascript
    assert b"`/api/articles/${article.id}/views`" in javascript
    assert (
        b"article.view_count = Math.max(Number.isSafeInteger(article.view_count) ? "
        b"article.view_count : 0, payload.view_count)" in javascript
    )
    assert b"Counting is best-effort" in javascript
    assert javascript.count(b"state.page = 1") >= 4
    assert javascript.count(b"requestGeneration !== articleRequestGeneration") == 2


def test_article_source_and_storage_json_endpoints(tmp_path: Path) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        article_status, article_headers, article_body = _request(
            server, "/api/articles?q=AI+%E6%9D%B1%E4%BA%AC&source=yahoo"
        )
        source_status, _, source_body = _request(server, "/api/sources")
        category_status, category_headers, category_body = _request(server, "/api/categories")
        storage_status, _, storage_body = _request(server, "/api/storage")
    finally:
        _stop_server(server, thread)

    articles = json.loads(article_body)
    sources = json.loads(source_body)["sources"]
    categories = json.loads(category_body)
    storage = json.loads(storage_body)
    assert article_status == source_status == category_status == storage_status == 200
    assert article_headers.get_content_type() == "application/json"
    assert article_headers["Cache-Control"] == "no-store"
    assert category_headers.get_content_type() == "application/json"
    assert category_headers["Cache-Control"] == "no-store"
    assert articles["total"] == 1
    assert articles["articles"][0]["timestamp_kind"] == "portal_provided"
    assert articles["articles"][0]["published_at"] is None
    assert articles["articles"][0]["view_count"] == 0
    assert len(sources) == 6
    assert categories == {"categories": ["IT"]}
    ledge = next(source for source in sources if source["id"] == "ledge_ai")
    assert ledge["status"] == "disabled"
    assert ledge["disabled_reason"] == "利用許可未確認のため取得しません"
    assert storage["total_bytes"] > 0


def test_article_category_filter_and_sort_are_backward_compatible(tmp_path: Path) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        default_status, _, default_body = _request(server, "/api/articles")
        category_status, _, category_body = _request(server, "/api/articles?category=IT&sort=views")
        exact_status, _, exact_body = _request(server, "/api/articles?category=it")
    finally:
        _stop_server(server, thread)

    assert default_status == category_status == exact_status == 200
    assert json.loads(default_body)["total"] == 1
    assert json.loads(category_body)["total"] == 1
    assert json.loads(exact_body)["total"] == 0


def test_article_view_post_increments_and_missing_id_returns_404(tmp_path: Path) -> None:
    server, thread, _ = _start_server(tmp_path)
    origin = _base_url(server)
    headers = {"Content-Type": "application/json", "Origin": origin}
    try:
        _, _, initial_body = _request(server, "/api/articles")
        article_id = json.loads(initial_body)["articles"][0]["id"]
        first_status, _, first_body = _request(
            server,
            f"/api/articles/{article_id}/views",
            method="POST",
            body=b"{}",
            headers=headers,
        )
        second_status, _, second_body = _request(
            server,
            f"/api/articles/{article_id}/views",
            method="POST",
            body=b"{}",
            headers=headers,
        )
        missing_status, _, missing_body = _request(
            server,
            "/api/articles/999999/views",
            method="POST",
            body=b"{}",
            headers=headers,
        )
        _, _, updated_body = _request(server, "/api/articles")
    finally:
        _stop_server(server, thread)

    assert first_status == second_status == 200
    assert json.loads(first_body)["view_count"] == 1
    assert json.loads(second_body)["view_count"] == 2
    assert missing_status == 404
    assert "記事" in json.loads(missing_body)["error"]
    assert json.loads(updated_body)["articles"][0]["view_count"] == 2


def test_article_view_post_rejects_cross_origin_without_incrementing(tmp_path: Path) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        _, _, initial_body = _request(server, "/api/articles")
        article_id = json.loads(initial_body)["articles"][0]["id"]
        status, _, body = _request(
            server,
            f"/api/articles/{article_id}/views",
            method="POST",
            body=b"{}",
            headers={"Content-Type": "application/json", "Origin": "http://evil.example"},
        )
        _, _, unchanged_body = _request(server, "/api/articles")
    finally:
        _stop_server(server, thread)

    assert status == 400
    assert "オリジン" in json.loads(body)["error"]
    assert json.loads(unchanged_body)["articles"][0]["view_count"] == 0


def test_article_view_posts_do_not_emit_identifying_access_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    server, thread, _ = _start_server(tmp_path)
    origin = _base_url(server)
    headers = {"Content-Type": "application/json", "Origin": origin}
    invalid_id = "private-id-abc"
    missing_id = "8765432109"
    try:
        _, _, initial_body = _request(server, "/api/articles")
        article_id = json.loads(initial_body)["articles"][0]["id"]
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="news_aggregator.interfaces.web"):
            control_status, _, _ = _request(server, "/api/storage")
            success_status, _, _ = _request(
                server,
                f"/api/articles/{article_id}/views",
                method="POST",
                body=b"{}",
                headers=headers,
            )
            invalid_status, _, _ = _request(
                server,
                f"/api/articles/{invalid_id}/views",
                method="POST",
                body=b"{}",
                headers=headers,
            )
            missing_status, _, _ = _request(
                server,
                f"/api/articles/{missing_id}/views",
                method="POST",
                body=b"{}",
                headers=headers,
            )
    finally:
        _stop_server(server, thread)

    log_messages = "\n".join(record.getMessage() for record in caplog.records)
    assert control_status == success_status == 200
    assert invalid_status == 400
    assert missing_status == 404
    assert '"GET /api/storage HTTP/1.1" 200' in log_messages
    assert f"/api/articles/{article_id}/views" not in log_messages
    assert invalid_id not in log_messages
    assert missing_id not in log_messages


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
        "/api/articles?sort=popular",
        "/api/articles?sort=",
        "/api/articles?sort=latest&sort=views",
        "/api/articles?category=",
        "/api/articles?category=%20",
        "/api/articles?category=" + "a" * 101,
        "/api/articles?category=IT&category=AI",
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


@pytest.mark.parametrize("article_id", ["0", "-1", "abc", "9223372036854775808"])
def test_invalid_article_view_ids_return_400(tmp_path: Path, article_id: str) -> None:
    server, thread, _ = _start_server(tmp_path)
    try:
        status, _, body = _request(
            server,
            f"/api/articles/{article_id}/views",
            method="POST",
            body=b"{}",
            headers={"Content-Type": "application/json", "Origin": _base_url(server)},
        )
    finally:
        _stop_server(server, thread)

    assert status == 400
    assert "記事ID" in json.loads(body)["error"]


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
