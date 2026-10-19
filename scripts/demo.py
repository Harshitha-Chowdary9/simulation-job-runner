"""End-to-end demo: real PostgreSQL + HTTP API + two workers, no Docker.

Usage:  PYTHONPATH=src python3 scripts/demo.py
Starts an ephemeral PostgreSQL (pgserver), the FastAPI app on 127.0.0.1:8377,
and two worker threads, then drives everything over real HTTP.
"""

from __future__ import annotations

import threading
import time

import httpx
import pgserver
import uvicorn

from simrunner.api import create_app
from simrunner.db import make_engine, make_session_factory
from simrunner.worker import Worker

BASE = "http://127.0.0.1:8377"


def main() -> None:
    srv = pgserver.get_server("/tmp/simrunner-demo-pg")
    import psycopg2
    conn = psycopg2.connect(srv.get_uri())
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("select 1 from pg_database where datname='simrunner_demo'")
    if not cur.fetchone():
        cur.execute("create database simrunner_demo")
    conn.close()
    db_url = srv.get_uri().replace("/postgres?", "/simrunner_demo?")
    print(f"PostgreSQL up: {db_url.split('?')[0]} (ephemeral)")

    app = create_app(db_url)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8377, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()

    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    workers = [Worker(factory, poll_seconds=0.2) for _ in range(2)]
    for w in workers:
        w.start()

    with httpx.Client(base_url=BASE, timeout=10) as http:
        for _ in range(50):
            try:
                http.get("/health")
                break
            except httpx.TransportError:
                time.sleep(0.1)
        print("API up:", http.get("/health").json())

        jobs = [
            {"nx": 60, "steps": 800},                      # normal
            {"nx": 40, "steps": 200, "left_temp": 80.0},   # different boundary
            {"dt": 100.0},                                 # unstable: must fail
        ]
        ids = []
        for params in jobs:
            r = http.post("/jobs", json={"params": params})
            r.raise_for_status()
            ids.append(r.json()["id"])
        print(f"submitted {len(ids)} jobs")

        deadline = time.time() + 60
        while time.time() < deadline:
            statuses = [http.get(f"/jobs/{i}").json()["status"] for i in ids]
            if all(s in ("succeeded", "failed", "cancelled") for s in statuses):
                break
            time.sleep(0.5)

        for i in ids:
            d = http.get(f"/jobs/{i}").json()
            line = f"job {d['id'][:8]}: {d['status']}"
            if d["status"] == "succeeded":
                solve = d["result"]["steps"]["solve"]
                line += f" | mean={solve['final_mean']}C after {solve['steps']} steps (r={solve['stability_ratio']})"
            else:
                line += f" | error: {d['error'][:80]}"
            print(line)
        print("workers processed:", sum(w.processed for w in workers), "jobs (2 workers)")

    for w in workers:
        w.stop()
    server.should_exit = True
    srv.cleanup()
    print("demo done")


if __name__ == "__main__":
    main()
