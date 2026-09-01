from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import news_aggregator.main as main_module
from news_aggregator.application.errors import FeedLoadError
from news_aggregator.application.services import NewsApplication
from news_aggregator.domain.models import (
    ArticleCandidate,
    FeedDefinition,
    SourceDefinition,
    SourceKind,
    TimestampKind,
)
from news_aggregator.infrastructure.sqlite_repository import SqliteArticleRepository
from news_aggregator.main import ApplicationComponents, build_application, create_argument_parser

NOW = datetime(2026, 8, 31, tzinfo=UTC)


class NoopLoader:
    def load(self, feed: FeedDefinition, *, fetched_at: datetime) -> tuple[ArticleCandidate, ...]:
        del feed, fetched_at
        return ()


class ErrorLoader:
    def load(self, feed: FeedDefinition, *, fetched_at: datetime) -> tuple[ArticleCandidate, ...]:
        del feed, fetched_at
        raise FeedLoadError("取得失敗")


def _source() -> SourceDefinition:
    return SourceDefinition(
        id="test",
        name="テスト",
        kind=SourceKind.DIRECT,
        timestamp_kind=TimestampKind.PUBLISHED,
        enabled=True,
        disabled_reason=None,
        terms_note="test",
        feeds=(FeedDefinition(id="feed", source_id="test", url="https://example.jp/feed"),),
    )


def _components(path: Path, *, error: bool = False) -> ApplicationComponents:
    repository = SqliteArticleRepository(path)
    repository.initialize()
    application = NewsApplication(
        repository=repository,
        feed_loader=ErrorLoader() if error else NoopLoader(),
        sources=(_source(),),
        clock=lambda: NOW,
    )
    return ApplicationComponents(repository=repository, application=application)


def test_build_application_initializes_database_without_starting_fetch(tmp_path: Path) -> None:
    components = build_application(db_path=tmp_path / "news.db", timeout_seconds=1)

    assert components.repository.path.exists()
    assert len(components.application.sources) == 6
    assert components.application.source_states()[0].status == "never"


def test_argument_parser_documents_serve_and_fetch_defaults() -> None:
    parser = create_argument_parser()

    serve = parser.parse_args(["serve"])
    fetch = parser.parse_args(["fetch", "--timeout", "2"])

    assert serve.host == "127.0.0.1"
    assert serve.port == 8765
    assert fetch.timeout == 2


@pytest.mark.parametrize(("error", "expected"), [(False, 0), (True, 1)])
def test_single_fetch_cli_writes_json_and_returns_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: bool,
    expected: int,
) -> None:
    components = _components(tmp_path / "news.db", error=error)
    monkeypatch.setattr(main_module, "build_application", lambda **_kwargs: components)

    exit_code = main_module.run(["fetch", "--db", str(tmp_path / "unused.db")])

    output = capsys.readouterr().out
    assert exit_code == expected
    assert '"has_errors"' in output
    assert '"feed_id": "feed"' in output


def test_main_converts_run_result_to_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "run", lambda _argv=None: 7)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 7
