"""The worker: claims queued jobs from PostgreSQL and runs their workflows.

Concurrency is handled by the database, not by Python locks:
SELECT ... FOR UPDATE SKIP LOCKED lets any number of workers (or processes,
or machines) share one queue without claiming the same job twice.

A job whose heartbeat goes stale while "running" (worker died) is requeued
by recover_stale_jobs(); its already-completed steps are kept, so the
workflow resumes instead of restarting.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Job, JobStatus, utcnow
from .workflow import WorkflowFailure, run_job

logger = logging.getLogger("simrunner.worker")


def claim_next_job(session: Session) -> Job | None:
    """Atomically claim one queued job; None when the queue is empty."""
    job = session.scalars(
        select(Job)
        .where(Job.status == JobStatus.queued)
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        return None
    job.status = JobStatus.running
    job.heartbeat_at = utcnow()
    session.flush()
    return job


def recover_stale_jobs(session: Session, stale_after_seconds: float) -> int:
    """Requeue 'running' jobs whose heartbeat is older than the threshold."""
    cutoff = utcnow() - timedelta(seconds=stale_after_seconds)
    stale = session.scalars(
        select(Job).where(
            Job.status == JobStatus.running,
            (Job.heartbeat_at == None) | (Job.heartbeat_at < cutoff),  # noqa: E711
        )
    ).all()
    for job in stale:
        job.status = JobStatus.queued
        job.heartbeat_at = None
    session.flush()
    return len(stale)


def work_once(session: Session, *, max_step_attempts: int = 3,
              sleep=time.sleep) -> bool:
    """Claim and process one job. Returns True if a job was processed."""
    job = claim_next_job(session)
    if job is None:
        return False
    try:
        run_job(session, job, max_step_attempts=max_step_attempts, sleep=sleep)
    except WorkflowFailure:
        pass  # job row already carries the failure state
    session.commit()
    return True


class Worker(threading.Thread):
    """A polling worker thread. Multiple Workers share the queue safely."""

    def __init__(self, session_factory, *, poll_seconds: float = 0.5,
                 stale_after_seconds: float = 30.0, max_step_attempts: int = 3):
        super().__init__(daemon=True)
        self.session_factory = session_factory
        self.poll_seconds = poll_seconds
        self.stale_after_seconds = stale_after_seconds
        self.max_step_attempts = max_step_attempts
        self._stop_event = threading.Event()
        self.processed = 0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self.session_factory() as session:
                    recover_stale_jobs(session, self.stale_after_seconds)
                    did_work = work_once(session, max_step_attempts=self.max_step_attempts)
                if did_work:
                    self.processed += 1
                else:
                    self._stop_event.wait(self.poll_seconds)
            except Exception:
                logger.exception("worker iteration failed; backing off")
                self._stop_event.wait(max(self.poll_seconds, 1.0))
