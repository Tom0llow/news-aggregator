from __future__ import annotations

import logging
import threading

import pytest

from news_aggregator.application.services import FetchInProgressError
from news_aggregator.infrastructure.scheduler import IntervalScheduler


def test_scheduler_runs_immediately_repeats_and_stops() -> None:
    second_call = threading.Event()
    state_lock = threading.Lock()
    calls = 0

    def task() -> None:
        nonlocal calls
        with state_lock:
            calls += 1
            if calls >= 2:
                second_call.set()

    scheduler = IntervalScheduler(task, interval_seconds=0.01)
    scheduler.start()
    scheduler.start()
    assert second_call.wait(1)
    assert scheduler.is_running

    scheduler.stop(timeout_seconds=1)

    assert not scheduler.is_running
    assert calls >= 2


def test_scheduler_contains_expected_and_unexpected_task_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    messages: list[Exception] = [FetchInProgressError(), RuntimeError("boom")]
    called = threading.Event()

    def task() -> None:
        error = messages.pop(0)
        if not messages:
            called.set()
        raise error

    scheduler = IntervalScheduler(task, interval_seconds=0.01)
    with caplog.at_level(logging.INFO):
        scheduler.start()
        assert called.wait(1)
        scheduler.stop(timeout_seconds=1)

    assert "取得処理が実行中" in caplog.text
    assert "スケジュールされたニュース取得に失敗" in caplog.text


def test_scheduler_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError, match="positive"):
        IntervalScheduler(lambda: None, interval_seconds=0)
