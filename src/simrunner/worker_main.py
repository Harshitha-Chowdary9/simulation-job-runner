"""Worker entrypoint: python -m simrunner.worker_main (used by docker-compose)."""

from __future__ import annotations

import time

from .config import Config
from .db import Base, make_engine, make_session_factory
from .worker import Worker


def main() -> None:
    config = Config.from_env()
    engine = make_engine(config.database_url)
    Base.metadata.create_all(engine)
    worker = Worker(
        make_session_factory(engine),
        poll_seconds=config.worker_poll_seconds,
        stale_after_seconds=config.stale_heartbeat_seconds,
        max_step_attempts=config.max_step_attempts,
    )
    worker.start()
    print("worker started; polling", config.database_url.split("?")[0])
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        worker.stop()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()
