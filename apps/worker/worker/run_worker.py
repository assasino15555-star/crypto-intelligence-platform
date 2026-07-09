"""Taskiq worker entrypoint.

Run with:
    python -m apps.worker.worker.run_worker

In production, replace the in-memory broker with the Redis broker (see
`taskiq_redis.RedisAsyncResultBackend`). For this release the in-memory broker
is sufficient to run all tasks; production deployment should switch to
TaskiqRedisBroker.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from apps.api.app.core.logging import configure_logging, get_logger
from apps.worker.worker.tasks import get_broker

log = get_logger(__name__)


async def main() -> None:
    configure_logging()
    broker = get_broker()
    log.info("worker started tasks=%s", list(broker._tasks.keys()))
    stop = asyncio.Event()

    def _stop(*_: object) -> None:
        log.info("worker shutdown requested")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _stop)
    await stop.wait()
    log.info("worker exited cleanly")


if __name__ == "__main__":
    asyncio.run(main())
