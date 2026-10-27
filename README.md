# simulation-job-runner

[![CI](https://github.com/Harshitha-Chowdary9/simulation-job-runner/actions/workflows/ci.yml/badge.svg)](https://github.com/Harshitha-Chowdary9/simulation-job-runner/actions/workflows/ci.yml)

A small Python backend for submitting and running simulation jobs: a FastAPI
REST service, PostgreSQL persistence, and workers that execute multi-step
**durable workflows** - the same shape as a real simulation platform's
backend, at honest toy scale.

> **Learning project.** Built by Harshitha Chittineni with AI-assistant
> pairing to practise backend engineering (Python services, PostgreSQL,
> REST, workflow orchestration). Not production software; no real CAE data.

## What it does

- **REST API (FastAPI)**: submit a simulation job, list/filter jobs, fetch a
  job with its workflow steps, cancel a job. Proper 404/409/422 handling.
- **A real numerical kernel**: 1D heat conduction solved with an explicit
  finite-difference (FTCS) scheme, including the CFL stability check
  (`alpha*dt/dx^2 <= 0.5`) - unstable grids are rejected at validation.
- **Durable workflow engine**: every job runs `validate -> mesh -> solve ->
  postprocess`. Each step's status, attempts and output are persisted to
  PostgreSQL as it completes. A worker that dies mid-job leaves completed
  steps intact; the next run **resumes** at the first unfinished step
  instead of restarting (the durable-execution idea behind Temporal,
  implemented here directly - see "What this does not claim").
- **PostgreSQL-backed queue**: workers claim jobs with
  `SELECT ... FOR UPDATE SKIP LOCKED`, so multiple workers/processes share
  one queue with no double-claiming - enforced by the database, tested with
  concurrent sessions.
- **Crash recovery**: a job stuck `running` with a stale heartbeat is
  requeued automatically and resumes its workflow.
- **Retry with backoff** per step; permanent failures mark the job failed
  with a clear error instead of disappearing.

## Run the tests (real PostgreSQL, no Docker needed)

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src python -m pytest
```

**28 tests, all passing** (run 2026-10-19, Python 3.10, PostgreSQL 16 via
`pgserver`). The suite starts a throwaway PostgreSQL server itself, so the
locking and SQL you see is exercised against the real dialect. It covers:
the solver (stability, physics sanity), the API (CRUD, filters, cancel,
404/409/422), workflow resume/retry/failure, row-lock claiming under
concurrency, and stale-job recovery.

## Run the whole thing end-to-end

```bash
PYTHONPATH=src python scripts/demo.py
```

Boots an ephemeral PostgreSQL, the API on `127.0.0.1:8377`, and **two
workers**, then submits 3 jobs over real HTTP. Output from the actual run
(2026-10-19):

```
job f06f8962: succeeded | mean=38.774072C after 800 steps (r=0.3481)
job 7d80cd73: succeeded | mean=26.042278C after 200 steps (r=0.1521)
job 0d070b8e: failed | error: step 'validate' failed after 3 attempt(s): unstable grid...
workers processed: 3 jobs (2 workers)
```

Against your own PostgreSQL instead:

```bash
export DATABASE_URL=postgresql://user:pass@localhost:5432/simjobs
PYTHONPATH=src uvicorn simrunner.api:create_app --factory &
PYTHONPATH=src python -m simrunner.worker_main &
curl -X POST localhost:8000/jobs -H 'Content-Type: application/json' \
  -d '{"params": {"nx": 60, "steps": 800}}'
curl localhost:8000/jobs
```

## Docker

`Dockerfile` and `docker-compose.yml` (postgres + api + worker) are
included as configuration. **They were not built or run** - the development
environment has no Docker runtime. The verified run paths are the two
sections above.

## What this project deliberately does not claim

- **No Temporal.** The workflow engine here is a from-scratch, small
  implementation of the same durable-execution idea (persisted steps,
  resume-after-crash). It is honest preparation for learning Temporal, not
  Temporal experience.
- **No Docker runtime verification** (config files only), no cloud
  deployment, no Kubernetes.
- The simulation is a 1D teaching kernel, not CFD.
- Single-node, polling-based worker; no distributed claims beyond what
  `SKIP LOCKED` genuinely provides.

See `STUDY_GUIDE.md` for how to explain every design decision in an
interview.
