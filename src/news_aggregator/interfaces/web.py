from __future__ import annotations

import ipaddress
import json
import logging
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit

from news_aggregator.application.services import FetchInProgressError, NewsApplication
from news_aggregator.domain.models import (
    Article,
    ArticleSearch,
    FeedFetchResult,
    FeedState,
    FetchReport,
    SourceState,
)

LOGGER = logging.getLogger(__name__)
MAX_REQUEST_BODY_BYTES = 1_024
MAX_QUERY_LENGTH = 500
MAX_KEYWORDS = 20

_STATIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8", "no-cache"),
    "/static/app.js": ("app.js", "text/javascript; charset=utf-8", "no-cache"),
    "/static/style.css": ("style.css", "text/css; charset=utf-8", "no-cache"),
}


class LocalNewsServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    allow_reuse_address = True


class NewsRequestHandler(BaseHTTPRequestHandler):
    application: ClassVar[NewsApplication]
    server_version = "NewsAggregator/0.1"
    sys_version = ""

    def do_GET(self) -> None:
        try:
            self._require_loopback_host()
            parsed = urlsplit(self.path)
            if parsed.path in _STATIC_ASSETS:
                self._serve_static(parsed.path)
            elif parsed.path == "/api/articles":
                self._serve_articles(parse_qs(parsed.query, keep_blank_values=True))
            elif parsed.path == "/api/sources":
                self._send_json(HTTPStatus.OK, {"sources": self._source_payload()})
            elif parsed.path == "/api/storage":
                usage = self.application.storage_usage()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "total_bytes": usage.total_bytes,
                        "files": [{"name": name, "bytes": size} for name, size in usage.files],
                    },
                )
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "見つかりません"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            LOGGER.exception("HTTP GET の処理に失敗しました")
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "内部エラーが発生しました"},
            )

    def do_POST(self) -> None:
        try:
            self._require_loopback_host()
            parsed = urlsplit(self.path)
            if parsed.path != "/api/fetch":
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "見つかりません"})
                return
            self._require_same_origin_json()
            report = self.application.fetch_all()
            self._send_json(HTTPStatus.OK, _fetch_report_payload(report))
        except FetchInProgressError as exc:
            self._send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            LOGGER.exception("HTTP POST の処理に失敗しました")
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "内部エラーが発生しました"},
            )

    def log_message(self, message_format: str, *args: object) -> None:
        LOGGER.info("HTTP %s", message_format % args)

    def _serve_static(self, path: str) -> None:
        name, content_type, cache_control = _STATIC_ASSETS[path]
        asset = resources.files("news_aggregator.interfaces.static").joinpath(name).read_bytes()
        self._send_bytes(
            HTTPStatus.OK,
            asset,
            content_type=content_type,
            cache_control=cache_control,
        )

    def _serve_articles(self, query: dict[str, list[str]]) -> None:
        raw_keywords = _single_query_value(query, "q")
        if len(raw_keywords) > MAX_QUERY_LENGTH:
            raise ValueError("検索キーワードが長すぎます")
        keywords = tuple(raw_keywords.split())
        if len(keywords) > MAX_KEYWORDS:
            raise ValueError("検索キーワードが多すぎます")
        source_id = _single_query_value(query, "source") or None
        valid_source_ids = {source.id for source in self.application.sources}
        if source_id is not None and source_id not in valid_source_ids:
            raise ValueError("未登録のニュースソースです")
        search = ArticleSearch(
            keywords=keywords,
            source_id=source_id,
            date_from=_optional_date(_single_query_value(query, "date_from")),
            date_to=_optional_date(_single_query_value(query, "date_to")),
            page=_positive_int(_single_query_value(query, "page"), default=1, name="page"),
            limit=_positive_int(_single_query_value(query, "limit"), default=30, name="limit"),
        )
        result = self.application.search(search)
        self._send_json(
            HTTPStatus.OK,
            {
                "articles": [_article_payload(article) for article in result.articles],
                "total": result.total,
                "page": result.page,
                "limit": result.limit,
            },
        )

    def _source_payload(self) -> list[dict[str, object]]:
        return [_source_state_payload(source) for source in self.application.source_states()]

    def _require_loopback_host(self) -> None:
        host_header = self.headers.get("Host")
        if host_header is None or not is_loopback_host_header(host_header):
            raise ValueError("loopback以外のHostは受け付けません")

    def _require_same_origin_json(self) -> None:
        if self.headers.get("Transfer-Encoding"):
            raise ValueError("Transfer-Encoding は使用できません")
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise ValueError("Content-Type は application/json にしてください")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length が必要です")
        try:
            content_length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Content-Length が不正です") from exc
        if not 0 <= content_length <= MAX_REQUEST_BODY_BYTES:
            raise ValueError("リクエスト本体が長すぎます")
        origin = self.headers.get("Origin")
        expected_origin = f"http://{self.headers['Host']}"
        if origin != expected_origin:
            raise ValueError("異なるオリジンからの操作は受け付けません")
        body = self.rfile.read(content_length)
        try:
            payload: object = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("JSONが不正です") from exc
        if not isinstance(payload, dict) or payload:
            raise ValueError("空のJSONオブジェクトを指定してください")

    def _send_json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(
            status,
            body,
            content_type="application/json; charset=utf-8",
            cache_control="no-store",
        )

    def _send_bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        *,
        content_type: str,
        cache_control: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'none'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(body)


def create_local_server(
    *,
    host: str,
    port: int,
    application: NewsApplication,
) -> LocalNewsServer:
    validate_loopback_bind(host)
    if not 0 <= port <= 65_535:
        raise ValueError("port は0から65535の範囲で指定してください")

    class ConfiguredNewsRequestHandler(NewsRequestHandler):
        pass

    ConfiguredNewsRequestHandler.application = application
    return LocalNewsServer((host, port), ConfiguredNewsRequestHandler)


def validate_loopback_bind(host: str) -> None:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("待受アドレスはloopbackのIPアドレスで指定してください") from exc
    if address.version != 4 or not address.is_loopback:
        raise ValueError("IPv4 loopback以外では待ち受けできません")


def is_loopback_host_header(value: str) -> bool:
    host = value.strip()
    if not host or "@" in host or "," in host:
        return False
    if host.startswith("["):
        return False
    hostname, separator, port = host.partition(":")
    if separator and (not port.isdigit() or not 0 <= int(port) <= 65_535):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.version == 4 and address.is_loopback


def _single_query_value(query: dict[str, list[str]], name: str) -> str:
    values = query.get(name, [""])
    if len(values) != 1:
        raise ValueError(f"{name} は1つだけ指定してください")
    return values[0]


def _optional_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("日付はYYYY-MM-DD形式で指定してください") from exc


def _positive_int(value: str, *, default: int, name: str) -> int:
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} は整数で指定してください") from exc
    if parsed < 1:
        raise ValueError(f"{name} は1以上で指定してください")
    if parsed > 1_000_000:
        raise ValueError(f"{name} が大きすぎます")
    return parsed


def _datetime_value(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value is not None else None


def _article_payload(article: Article) -> dict[str, object]:
    return {
        "id": article.id,
        "title": article.title,
        "summary": article.summary,
        "url": article.url,
        "source_id": article.source_id,
        "source_name": article.source_name,
        "publisher": article.publisher,
        "source_kind": article.source_kind.value,
        "published_at": _datetime_value(article.published_at),
        "timestamp_kind": article.timestamp_kind.value,
        "fetched_at": _datetime_value(article.fetched_at),
        "category": article.category,
        "tags": list(article.tags),
    }


def _feed_state_payload(feed: FeedState) -> dict[str, object]:
    return {
        "id": feed.id,
        "category": feed.category,
        "status": feed.status,
        "last_attempt_at": _datetime_value(feed.last_attempt_at),
        "last_success_at": _datetime_value(feed.last_success_at),
        "error": feed.error,
        "articles_seen": feed.articles_seen,
        "articles_inserted": feed.articles_inserted,
        "skipped_reason": feed.skipped_reason,
    }


def _source_state_payload(source: SourceState) -> dict[str, object]:
    return {
        "id": source.id,
        "name": source.name,
        "source_kind": source.kind.value,
        "enabled": source.enabled,
        "disabled_reason": source.disabled_reason,
        "terms_note": source.terms_note,
        "status": source.status,
        "last_attempt_at": _datetime_value(source.last_attempt_at),
        "last_success_at": _datetime_value(source.last_success_at),
        "error": source.error,
        "feeds": [_feed_state_payload(feed) for feed in source.feeds],
    }


def _fetch_result_payload(result: FeedFetchResult) -> dict[str, object]:
    return {
        "feed_id": result.feed_id,
        "source_id": result.source_id,
        "status": result.status,
        "articles_seen": result.articles_seen,
        "articles_inserted": result.articles_inserted,
        "error": result.error,
        "skipped_reason": result.skipped_reason,
    }


def _fetch_report_payload(report: FetchReport) -> dict[str, object]:
    return {
        "started_at": _datetime_value(report.started_at),
        "finished_at": _datetime_value(report.finished_at),
        "has_errors": report.has_errors,
        "results": [_fetch_result_payload(result) for result in report.results],
    }
