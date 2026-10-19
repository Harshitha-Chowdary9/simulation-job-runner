import uuid


def submit(client, params=None):
    return client.post("/jobs", json={"params": params or {"nx": 20, "steps": 50}})


class TestHealth:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}


class TestJobsApi:
    def test_create_and_fetch(self, client):
        created = submit(client)
        assert created.status_code == 201
        body = created.json()
        assert body["status"] == "queued"
        assert body["params"]["nx"] == 20

        detail = client.get(f"/jobs/{body['id']}")
        assert detail.status_code == 200
        assert detail.json()["steps"] == []  # steps appear once a worker runs it

    def test_list_and_status_filter(self, client):
        submit(client)
        submit(client, {"nx": 10, "steps": 5})
        assert len(client.get("/jobs").json()) == 2
        assert len(client.get("/jobs", params={"status": "queued"}).json()) == 2
        assert client.get("/jobs", params={"status": "succeeded"}).json() == []

    def test_unknown_status_filter_is_422(self, client):
        assert client.get("/jobs", params={"status": "nope"}).status_code == 422

    def test_unknown_job_is_404(self, client):
        assert client.get(f"/jobs/{uuid.uuid4()}").status_code == 404

    def test_cancel_queued_job(self, client):
        job_id = submit(client).json()["id"]
        cancelled = client.post(f"/jobs/{job_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

    def test_cancel_finished_job_conflicts(self, client, session_factory):
        job_id = submit(client).json()["id"]
        client.post(f"/jobs/{job_id}/cancel")
        assert client.post(f"/jobs/{job_id}/cancel").status_code == 409


class TestEndToEndThroughApi:
    def test_worker_completes_api_created_job(self, client, session_factory):
        job_id = submit(client).json()["id"]

        from simrunner.worker import work_once
        with session_factory() as session:
            assert work_once(session, sleep=lambda s: None) is True

        detail = client.get(f"/jobs/{job_id}").json()
        assert detail["status"] == "succeeded"
        assert [s["name"] for s in detail["steps"]] == ["validate", "mesh", "solve", "postprocess"]
        assert all(s["status"] == "succeeded" for s in detail["steps"])
