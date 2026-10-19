"""A small durable workflow engine.

The idea mirrors durable-execution frameworks (Temporal and friends) at toy
scale: a workflow is an ordered list of named steps; every step's outcome is
persisted to PostgreSQL as it completes. If the worker dies mid-workflow,
the next run resumes at the first step that did not succeed - completed
steps are never re-executed.

Steps are plain Python functions with a (params, prior_outputs) -> dict
signature, which keeps the engine honest and testable.
"""

from __future__ import annotations

import time
from typing import Callable

from sqlalchemy.orm import Session

from .models import Job, JobStatus, StepStatus, WorkflowStep, utcnow
from .simulation import SimulationParams, check_params, solve_heat_1d

StepFn = Callable[[dict, dict], dict]


def _validate(params: dict, prior: dict) -> dict:
    p = SimulationParams.from_dict(params)
    check_params(p)
    return {"validated": True, "stability_ratio": round(
        p.diffusivity * p.dt * (p.nx - 1) ** 2, 6)}


def _mesh(params: dict, prior: dict) -> dict:
    p = SimulationParams.from_dict(params)
    return {"nx": p.nx, "dx": round(1.0 / (p.nx - 1), 8), "points": p.nx}


def _solve(params: dict, prior: dict) -> dict:
    return solve_heat_1d(SimulationParams.from_dict(params))


def _postprocess(params: dict, prior: dict) -> dict:
    solve_out = prior["solve"]
    return {
        "summary": (
            f"1D heat conduction: mean interior temperature "
            f"{solve_out['final_mean']} after {solve_out['steps']} steps"
        ),
        "converged_below_initial": solve_out["final_max"] <= 100.0,
    }


STEP_FUNCTIONS: list[tuple[str, StepFn]] = [
    ("validate", _validate),
    ("mesh", _mesh),
    ("solve", _solve),
    ("postprocess", _postprocess),
]


class WorkflowFailure(Exception):
    """A step failed permanently (no retries left)."""


def ensure_step_rows(session: Session, job: Job) -> list[WorkflowStep]:
    if job.steps:
        return job.steps
    steps = [
        WorkflowStep(job_id=job.id, step_index=i, name=name, status=StepStatus.pending)
        for i, (name, _) in enumerate(STEP_FUNCTIONS)
    ]
    session.add_all(steps)
    session.flush()
    job.steps = steps
    return steps


def run_job(session: Session, job: Job, *, max_step_attempts: int = 3,
            sleep: Callable[[float], None] = time.sleep) -> Job:
    """Run (or resume) a job's workflow to completion or permanent failure."""
    steps = ensure_step_rows(session, job)
    prior_outputs = {
        step.name: step.output for step in steps if step.status == StepStatus.succeeded
    }

    for step, (name, fn) in zip(steps, STEP_FUNCTIONS):
        if step.status == StepStatus.succeeded:
            continue  # resume: never redo completed work
        # Test/chaos hook: params may request one injected failure at a step.
        fail_once = job.params.get("_fail_once_at") == name

        step.status = StepStatus.running
        session.flush()
        try:
            output = None
            while True:
                step.attempts += 1
                try:
                    if fail_once:
                        fail_once = False
                        raise RuntimeError(f"injected failure at step '{name}'")
                    output = fn(job.params, prior_outputs)
                    break
                except Exception:
                    session.flush()
                    if step.attempts >= max_step_attempts:
                        raise
                    sleep(0.1 * step.attempts)  # small linear backoff
            step.output = output
            step.status = StepStatus.succeeded
            step.error = None
            prior_outputs[name] = output
        except Exception as exc:
            step.status = StepStatus.failed
            step.error = str(exc)[:500]
            job.status = JobStatus.failed
            job.error = f"step '{name}' failed after {step.attempts} attempt(s): {exc}"[:500]
            session.flush()
            raise WorkflowFailure(job.error) from exc
        finally:
            job.heartbeat_at = utcnow()
            session.flush()

    job.status = JobStatus.succeeded
    job.result = {
        "steps": {s.name: s.output for s in steps},
        "summary": prior_outputs["postprocess"]["summary"],
    }
    job.error = None
    session.flush()
    return job
