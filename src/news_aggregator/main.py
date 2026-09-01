from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from news_aggregator.application.services import NewsApplication
from news_aggregator.infrastructure.rss import HttpFeedClient, RssFeedLoader, RssParser
from news_aggregator.infrastructure.scheduler import IntervalScheduler
from news_aggregator.infrastructure.source_catalog import allowed_feed_urls, default_sources
from news_aggregator.infrastructure.sqlite_repository import SqliteArticleRepository
from news_aggregator.interfaces.web import create_local_server, validate_loopback_bind

DEFAULT_DB_PATH = Path("data/news.db")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


@dataclass(frozen=True, slots=True)
class ApplicationComponents:
    repository: SqliteArticleRepository
    application: NewsApplication


def build_application(*, db_path: Path, timeout_seconds: float = 15.0) -> ApplicationComponents:
    """Construct and initialize the application without starting background work."""

    sources = default_sources()
    repository = SqliteArticleRepository(db_path)
    repository.initialize()
    client = HttpFeedClient(
        allowed_urls=allowed_feed_urls(sources),
        timeout_seconds=timeout_seconds,
    )
    loader = RssFeedLoader(client=client, parser=RssParser(), sources=sources)
    application = NewsApplication(
        repository=repository,
        feed_loader=loader,
        sources=sources,
    )
    return ApplicationComponents(repository=repository, application=application)


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="news-aggregator",
        description="個人用ローカル日本語ニュース集計アプリ",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="ローカルWebアプリを起動")
    serve.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite DBの保存先")
    serve.add_argument("--host", default=DEFAULT_HOST, help="IPv4 loopbackアドレス")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT, help="待受ポート")
    serve.add_argument("--timeout", type=float, default=15.0, help="フィードHTTP timeout [秒]")

    fetch = subparsers.add_parser("fetch", help="全フィードを1回取得")
    fetch.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite DBの保存先")
    fetch.add_argument("--timeout", type=float, default=15.0, help="フィードHTTP timeout [秒]")
    return parser


def run(argv: list[str] | None = None) -> int:
    arguments = create_argument_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if arguments.command == "serve":
        return _serve(
            db_path=arguments.db,
            host=arguments.host,
            port=arguments.port,
            timeout_seconds=arguments.timeout,
        )
    if arguments.command == "fetch":
        return _fetch(db_path=arguments.db, timeout_seconds=arguments.timeout)
    raise AssertionError("argparse accepted an unknown command")


def _serve(*, db_path: Path, host: str, port: int, timeout_seconds: float) -> int:
    validate_loopback_bind(host)
    components = build_application(db_path=db_path, timeout_seconds=timeout_seconds)
    server = create_local_server(host=host, port=port, application=components.application)
    scheduler = IntervalScheduler(components.application.fetch_all)
    actual_port = int(server.server_address[1])
    logging.getLogger(__name__).info("http://%s:%d で起動しました", host, actual_port)
    try:
        scheduler.start()
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("終了要求を受け付けました")
    finally:
        server.server_close()
        scheduler.stop()
    return 0


def _fetch(*, db_path: Path, timeout_seconds: float) -> int:
    components = build_application(db_path=db_path, timeout_seconds=timeout_seconds)
    report = components.application.fetch_all()
    payload = {
        "started_at": report.started_at.isoformat(),
        "finished_at": report.finished_at.isoformat(),
        "has_errors": report.has_errors,
        "results": [
            {
                "feed_id": result.feed_id,
                "source_id": result.source_id,
                "status": result.status,
                "articles_seen": result.articles_seen,
                "articles_inserted": result.articles_inserted,
                "error": result.error,
                "skipped_reason": result.skipped_reason,
            }
            for result in report.results
        ],
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 1 if report.has_errors else 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
