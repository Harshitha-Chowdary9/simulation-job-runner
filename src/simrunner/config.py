"""Runtime configuration, from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    database_url: str
    worker_poll_seconds: float = 0.5
    stale_heartbeat_seconds: float = 30.0
    max_step_attempts: int = 3

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            database_url=os.environ.get(
                "DATABASE_URL",
                "postgresql://postgres@/simjobs?host=/tmp/pgsim-data",
            ),
            worker_poll_seconds=float(os.environ.get("WORKER_POLL_SECONDS", "0.5")),
            stale_heartbeat_seconds=float(os.environ.get("STALE_HEARTBEAT_SECONDS", "30")),
            max_step_attempts=int(os.environ.get("MAX_STEP_ATTEMPTS", "3")),
        )
