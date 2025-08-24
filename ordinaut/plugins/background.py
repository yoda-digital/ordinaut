from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional


def _now() -> float:
    return time.time()


def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 300.0) -> float:
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    # 50-100% jitter
    return delay * (0.5 + (attempt % 50) / 50.0)


@dataclass
class PeriodicTask:
    plugin_id: str
    name: str
    func: Callable[[], Awaitable[Any]] | Callable[[], Any]
    interval_s: float
    max_concurrency: int = 1
    _next_at: float = 0.0
    _running: int = 0
    _failures: int = 0


class BackgroundTaskSupervisor:
    """Simple background task scheduler with quotas per task.

    Not a general scheduler; meant for lightweight plugin maintenance tasks only.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, PeriodicTask] = {}
        self._running = False
        self._lock = asyncio.Lock()
        self._loop_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._loop_task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except Exception:
                pass

    async def register_periodic(
        self,
        *,
        plugin_id: str,
        name: str,
        func: Callable[[], Awaitable[Any]] | Callable[[], Any],
        interval_s: float,
        max_concurrency: int = 1,
    ) -> None:
        key = f"{plugin_id}:{name}"
        async with self._lock:
            if key in self._tasks:
                raise ValueError(f"task already exists: {key}")
            self._tasks[key] = PeriodicTask(
                plugin_id=plugin_id,
                name=name,
                func=func,
                interval_s=interval_s,
                max_concurrency=max_concurrency,
                _next_at=_now() + interval_s,
            )

    async def _run_loop(self) -> None:
        try:
            while self._running:
                now = _now()
                async with self._lock:
                    items = list(self._tasks.items())
                for key, t in items:
                    if t._running >= t.max_concurrency:
                        continue
                    if t._next_at > now:
                        continue
                    t._running += 1
                    asyncio.create_task(self._run_task(key, t))
                await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            return

    async def _run_task(self, key: str, t: PeriodicTask) -> None:
        try:
            res = t.func()
            if asyncio.iscoroutine(res):
                await res
            # Reset failure backoff on success
            t._failures = 0
            t._next_at = _now() + t.interval_s
        except Exception:
            # Backoff with jitter on failure
            t._failures += 1
            t._next_at = _now() + exponential_backoff(t._failures, base_delay=max(1.0, t.interval_s / 2))
        finally:
            t._running -= 1

