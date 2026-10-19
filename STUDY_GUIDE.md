# Study guide - simulation-job-runner

Run it before any interview (15 minutes):

1. `PYTHONPATH=src python -m pytest -v` - the test names are the spec.
2. `PYTHONPATH=src python scripts/demo.py` - watch two workers split three
   jobs, including one job that fails validation honestly.
3. Submit a job yourself with curl against your own run.

## Questions you should be able to answer

- **Why PostgreSQL for the queue instead of Redis/RabbitMQ?** One less
  moving part at this scale, and the database gives atomic claiming for
  free: `SELECT ... FOR UPDATE SKIP LOCKED` locks one queued row and skips
  rows other workers hold, so N workers never grab the same job. The
  concurrency test proves this with two concurrent sessions.
- **What does "durable workflow" mean here?** Every step's outcome is a row
  in PostgreSQL. Crash recovery = requeue stale-heartbeat jobs; resume =
  skip steps already marked succeeded. That is the same core idea Temporal
  industrialises (event-sourced history, replay) - be ready to say honestly
  that this project implements the *idea* at small scale and that you want
  to learn Temporal proper.
- **Why is validation a workflow step?** Fail fast with a clear error. The
  CFL condition (`alpha*dt/dx^2 <= 0.5`) decides whether the explicit scheme
  is even meaningful; checking it inside `solve` would mix concerns.
- **What happens when a step throws?** Retry with linear backoff up to
  `max_step_attempts`, then the job is marked failed with the step name and
  error. Transient vs permanent is decided by attempt count here; in
  production you'd also classify the exception.
- **What would you add before production?** Temporal or a real task queue,
  structured logging/tracing, API auth, pagination beyond 100, migrations
  (Alembic), CI, containerised deploy. Know that this project stops before
  those on purpose.

## Skills this project genuinely demonstrates

- Python 3 services: FastAPI app factory, Pydantic schemas, dependency
  injection of DB sessions, uvicorn.
- PostgreSQL: SQLAlchemy 2.0 typed models, JSONB, transactional queue with
  `FOR UPDATE SKIP LOCKED`, concurrent-session behaviour.
- REST API design: resources, status codes (201/404/409/422), filtering.
- Workflow orchestration concepts: durable steps, resume, retries with
  backoff, stale-job recovery, heartbeat.
- Numerical computing basics: explicit finite differences and the CFL
  stability condition.
- Testing with pytest against a real ephemeral PostgreSQL: API tests,
  concurrency tests, recovery tests, parametrized validation.
- Docker compose configuration for a db+api+worker stack (config only,
  honestly labelled).
