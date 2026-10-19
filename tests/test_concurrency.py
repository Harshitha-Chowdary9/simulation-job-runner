"""Concurrency and recovery semantics, exercised against real PostgreSQL."""

import threading

from simrunner.models import Job, JobStatus, utcnow
from simrunner.worker import claim_next_job, recover_stale_jobs, work_once
from datetime import timedelta


def add_jobs(session, n):
    for _ in range(n):
        session.add(Job(params={"nx": 15, "steps": 20}))
    session.flush()


class TestClaiming:
    def test_two_sessions_never_claim_the_same_job(self, engine, session_factory):
        with session_factory() as s:
            add_jobs(s, 1)
            s.commit()

        with session_factory() as s1, session_factory() as s2:
            first = claim_next_job(s1)   # holds the row lock (no commit yet)
            second = claim_next_job(s2)  # must skip the locked row
            assert first is not None
            assert second is None

    def test_workers_split_the_queue_without_overlap(self, session_factory):
        with session_factory() as s:
            add_jobs(s, 6)
            s.commit()

        claimed_ids = []
        lock = threading.Lock()

        def worker():
            while True:
                with session_factory() as s:
                    job = claim_next_job(s)
                    if job is None:
                        return
                    with lock:
                        claimed_ids.append(job.id)
                    job.status = JobStatus.succeeded
                    s.commit()

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=60)

        assert len(claimed_ids) == 6
        assert len(set(claimed_ids)) == 6  # no job claimed twice


class TestRecovery:
    def test_stale_running_job_is_requeued(self, session):
        job = Job(params={"nx": 15, "steps": 20}, status=JobStatus.running,
                  heartbeat_at=utcnow() - timedelta(seconds=3600))
        session.add(job)
        session.flush()
        assert recover_stale_jobs(session, stale_after_seconds=30) == 1
        assert job.status == JobStatus.queued
        assert job.heartbeat_at is None

    def test_fresh_running_job_is_left_alone(self, session):
        job = Job(params={}, status=JobStatus.running, heartbeat_at=utcnow())
        session.add(job)
        session.flush()
        assert recover_stale_jobs(session, stale_after_seconds=30) == 0
        assert job.status == JobStatus.running

    def test_requeued_job_resumes_and_completes(self, session):
        job = Job(params={"nx": 15, "steps": 20}, status=JobStatus.running,
                  heartbeat_at=utcnow() - timedelta(seconds=3600))
        session.add(job)
        session.flush()
        recover_stale_jobs(session, stale_after_seconds=30)
        session.commit()
        assert work_once(session, sleep=lambda s: None) is True
        assert job.status == JobStatus.succeeded
