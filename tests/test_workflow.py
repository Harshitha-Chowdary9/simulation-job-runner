import pytest

from simrunner.models import Job, JobStatus, StepStatus, utcnow
from simrunner.workflow import STEP_FUNCTIONS, WorkflowFailure, ensure_step_rows, run_job

NO_SLEEP = lambda s: None


def make_job(session, params=None):
    job = Job(params=params or {"nx": 20, "steps": 50})
    session.add(job)
    session.flush()
    return job


class TestHappyPath:
    def test_runs_all_steps_and_succeeds(self, session):
        job = make_job(session)
        run_job(session, job, sleep=NO_SLEEP)
        assert job.status == JobStatus.succeeded
        assert [s.status for s in job.steps] == [StepStatus.succeeded] * 4
        assert [s.name for s in job.steps] == [n for n, _ in STEP_FUNCTIONS]
        assert "summary" in job.result
        assert job.result["steps"]["solve"]["final_mean"] > 0

    def test_step_outputs_chain(self, session):
        job = make_job(session)
        run_job(session, job, sleep=NO_SLEEP)
        # postprocess consumed solve's output
        assert "mean interior temperature" in job.result["steps"]["postprocess"]["summary"]


class TestRetryAndFailure:
    def test_injected_failure_is_retried_once(self, session):
        job = make_job(session, {"nx": 20, "steps": 50, "_fail_once_at": "solve"})
        run_job(session, job, sleep=NO_SLEEP)
        assert job.status == JobStatus.succeeded
        solve = next(s for s in job.steps if s.name == "solve")
        assert solve.attempts == 2  # one injected failure + one success

    def test_permanent_failure_marks_job_failed(self, session):
        job = make_job(session, {"dt": 100.0})  # unstable: validate keeps failing
        with pytest.raises(WorkflowFailure):
            run_job(session, job, max_step_attempts=2, sleep=NO_SLEEP)
        assert job.status == JobStatus.failed
        validate = next(s for s in job.steps if s.name == "validate")
        assert validate.attempts == 2
        assert "unstable" in job.error


class TestResume:
    def test_completed_steps_are_not_reexecuted(self, session):
        job = make_job(session)
        steps = ensure_step_rows(session, job)
        # simulate a crashed run: first two steps done, worker died mid-run
        steps[0].status = StepStatus.succeeded
        steps[0].attempts = 1
        steps[0].output = {"validated": True, "stability_ratio": 0.1}
        steps[1].status = StepStatus.succeeded
        steps[1].attempts = 1
        steps[1].output = {"nx": 20, "dx": 0.05, "points": 20}
        steps[2].status = StepStatus.running  # died here
        session.flush()

        run_job(session, job, sleep=NO_SLEEP)
        assert job.status == JobStatus.succeeded
        assert job.steps[0].attempts == 1  # untouched
        assert job.steps[1].attempts == 1  # untouched
        assert job.steps[2].attempts >= 1  # re-executed after the "crash"
