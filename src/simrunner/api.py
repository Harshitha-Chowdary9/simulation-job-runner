"""FastAPI application: submit, inspect, list and cancel simulation jobs."""

from __future__ import annotations

import uuid

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .db import Base, make_engine, make_session_factory
from .models import Job, JobStatus
from .schemas import JobCreate, JobDetail, JobOut


def create_app(database_url: str) -> FastAPI:
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    SessionLocal = make_session_factory(engine)

    app = FastAPI(title="simulation-job-runner", version="0.1.0")

    def get_session():
        with SessionLocal() as session:
            yield session

    def get_job_or_404(job_id: uuid.UUID, session: Session) -> Job:
        job = session.get(Job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/jobs", response_model=JobOut, status_code=201)
    def create_job(payload: JobCreate, session: Session = Depends(get_session)):
        if not isinstance(payload.params, dict):
            raise HTTPException(status_code=422, detail="params must be an object")
        job = Job(params=payload.params)
        session.add(job)
        session.commit()
        return job

    @app.get("/jobs", response_model=list[JobOut])
    def list_jobs(status: str | None = Query(default=None),
                  session: Session = Depends(get_session)):
        stmt = select(Job).order_by(Job.created_at.desc()).limit(100)
        if status is not None:
            try:
                stmt = stmt.where(Job.status == JobStatus(status))
            except ValueError:
                raise HTTPException(status_code=422, detail=f"unknown status: {status}")
        return session.scalars(stmt).all()

    @app.get("/jobs/{job_id}", response_model=JobDetail)
    def get_job(job_id: uuid.UUID, session: Session = Depends(get_session)):
        return get_job_or_404(job_id, session)

    @app.post("/jobs/{job_id}/cancel", response_model=JobOut)
    def cancel_job(job_id: uuid.UUID, session: Session = Depends(get_session)):
        job = get_job_or_404(job_id, session)
        if job.status in (JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled):
            raise HTTPException(status_code=409, detail=f"job already {job.status.value}")
        job.status = JobStatus.cancelled
        session.commit()
        return job

    return app
