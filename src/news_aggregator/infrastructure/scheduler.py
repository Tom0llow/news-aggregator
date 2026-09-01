from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from news_aggregator.application.services import FetchInProgressError

LOGGER = logging.getLogger(__name__)
DEFAULT_FETCH_INTERVAL_SECONDS = 30 * 60


class IntervalScheduler:
    """Run one task immediately and then at a fixed in-process interval."""

    def __init__(
        self,
        task: Callable[[], object],
        *,
        interval_seconds: float = DEFAULT_FETCH_INTERVAL_SECONDS,
        thread_name: str = "news-fetch-scheduler",
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("scheduler interval must be positive")
        self._task = task
        self._interval_seconds = interval_seconds
        self._thread_name = thread_name
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()

    def start(self) -> None:
        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name=self._thread_name,
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout_seconds: float | None = None) -> None:
        self._stop_event.set()
        with self._state_lock:
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout_seconds)

    @property
    def is_running(self) -> bool:
        with self._state_lock:
            return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        self._run_task()
        while not self._stop_event.wait(self._interval_seconds):
            self._run_task()

    def _run_task(self) -> None:
        try:
            self._task()
        except FetchInProgressError:
            LOGGER.info("取得処理が実行中のためスケジュール実行を見送りました")
        except Exception:
            LOGGER.exception("スケジュールされたニュース取得に失敗しました")
