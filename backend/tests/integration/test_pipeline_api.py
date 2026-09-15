class TestRunPipeline:
    def _ingest_brute_force(self, test_client):
        for i in range(10):
            second = i * 20
            test_client.post(
                "/api/v1/events/auth",
                json={
                    "timestamp": f"2026-01-15T03:{second // 60:02d}:{second % 60:02d}Z",
                    "host": "db01.internal",
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "auth_method": "password",
                },
            )

    def _run_and_wait(self, test_client, payload=None):
        """TestClient runs BackgroundTasks synchronously before .post()
        returns, so by the time this returns, the job is already
        completed/failed — the POST response itself still reflects
        "pending" (serialized before the background task runs), so tests
        fetch the job afterward rather than asserting on the POST body.
        """
        response = test_client.post("/api/v1/pipeline/run", json=payload)
        assert response.status_code == 202
        job_id = response.json()["id"]
        return test_client.get(f"/api/v1/pipeline/jobs/{job_id}").json()

    def test_run_with_no_body_processes_existing_events(self, client):
        test_client, _ = client
        self._ingest_brute_force(test_client)

        job = self._run_and_wait(test_client)

        assert job["status"] == "completed"
        assert job["job_type"] == "pipeline_run"
        body = job["result"]
        assert body["detection"]["alerts_created"] == 1
        assert body["ioc"]["iocs_created"] >= 1
        assert body["correlation"]["incidents_created"] == 1
        assert body["triage"]["incidents_processed"] == 1
        assert body["triage"]["analysis_results_created"] > 0

    def test_run_produces_a_real_incident_visible_via_the_incidents_api(self, client):
        test_client, _ = client
        self._ingest_brute_force(test_client)

        self._run_and_wait(test_client)

        incidents = test_client.get("/api/v1/incidents").json()
        assert incidents["total"] == 1
        incident_id = incidents["items"][0]["id"]

        detail = test_client.get(f"/api/v1/incidents/{incident_id}").json()
        assert len(detail["alerts"]) == 1
        assert len(detail["analysis_results"]) > 0
        # MITRE mapping ran as part of the pipeline, but no MITRETechnique
        # rows were loaded (that's app.mitre.cli's job, not this endpoint's)
        # — so the rollup is empty rather than populated. Documents the
        # boundary rather than asserting something untrue.
        assert detail["mitre_techniques"] == []

    def test_since_filter_is_accepted(self, client):
        test_client, _ = client
        self._ingest_brute_force(test_client)

        job = self._run_and_wait(test_client, {"since": "2026-01-16T00:00:00Z"})
        assert job["status"] == "completed"
        assert job["result"]["detection"]["alerts_created"] == 0

    def test_run_with_no_events_is_a_no_op(self, client):
        test_client, _ = client
        job = self._run_and_wait(test_client)
        assert job["status"] == "completed"
        assert job["result"]["detection"]["alerts_created"] == 0
        assert job["result"]["correlation"]["incidents_created"] == 0

    def test_run_returns_a_pending_job_immediately(self, client):
        test_client, _ = client
        response = test_client.post("/api/v1/pipeline/run")
        assert response.status_code == 202
        body = response.json()
        assert body["job_type"] == "pipeline_run"
        # The response is serialized before the background task runs, so
        # it reflects the job's initial state, not its eventual outcome.
        assert body["status"] in {"pending", "running", "completed"}
        assert body["result"] is None or body["status"] == "completed"

    def test_unknown_job_id_returns_404(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/pipeline/jobs/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestReanalyze:
    """POST /pipeline/reanalyze — force-regenerates AI triage only,
    without redoing the (already-idempotent) deterministic stages. Added
    post-roadmap for a dashboard "Reanalyze" action distinct from the full
    "Run pipeline" — see DEF.md § Phase 9, "Reanalyze (post-roadmap)", and
    both endpoints now schedule their work as a background job rather than
    blocking the request — see DEF.md § Phase 9, "Post-roadmap addition:
    background pipeline jobs".
    """

    def _ingest_brute_force(self, test_client):
        for i in range(10):
            second = i * 20
            test_client.post(
                "/api/v1/events/auth",
                json={
                    "timestamp": f"2026-01-15T03:{second // 60:02d}:{second % 60:02d}Z",
                    "host": "db01.internal",
                    "event_result": "failure",
                    "username": "admin",
                    "source_ip": "198.51.100.1",
                    "auth_method": "password",
                },
            )

    def _run_pipeline_and_wait(self, test_client, payload=None):
        response = test_client.post("/api/v1/pipeline/run", json=payload)
        job_id = response.json()["id"]
        return test_client.get(f"/api/v1/pipeline/jobs/{job_id}").json()

    def _reanalyze_and_wait(self, test_client, payload=None):
        response = test_client.post("/api/v1/pipeline/reanalyze", json=payload)
        assert response.status_code == 202
        job_id = response.json()["id"]
        return test_client.get(f"/api/v1/pipeline/jobs/{job_id}").json()

    def test_reanalyze_regenerates_ai_results_that_already_exist(self, client):
        test_client, _ = client
        self._ingest_brute_force(test_client)
        self._run_pipeline_and_wait(test_client)

        incident_id = test_client.get("/api/v1/incidents").json()["items"][0]["id"]
        first_result_id = test_client.get(f"/api/v1/incidents/{incident_id}").json()[
            "analysis_results"
        ][0]["id"]

        # A plain pipeline re-run skips triage for work already done...
        rerun = self._run_pipeline_and_wait(test_client)
        assert rerun["result"]["triage"]["analysis_results_created"] == 0
        assert rerun["result"]["triage"]["analysis_results_skipped"] > 0

        # ...but reanalyze forces it, replacing the earlier result.
        job = self._reanalyze_and_wait(test_client)
        assert job["status"] == "completed"
        assert job["job_type"] == "triage_reanalyze"
        body = job["result"]
        assert body["analysis_results_created"] > 0
        assert body["analysis_results_skipped"] == 0

        detail = test_client.get(f"/api/v1/incidents/{incident_id}").json()
        new_result_ids = {r["id"] for r in detail["analysis_results"]}
        assert first_result_id not in new_result_ids

    def test_reanalyze_does_not_rerun_detection_or_correlation(self, client):
        test_client, _ = client
        self._ingest_brute_force(test_client)
        self._run_pipeline_and_wait(test_client)

        job = self._reanalyze_and_wait(test_client)
        assert job["status"] == "completed"
        assert set(job["result"].keys()) == {
            "since",
            "incidents_processed",
            "analysis_results_created",
            "analysis_results_skipped",
            "recommendations_created",
            "mitre_mappings_created",
            "by_task_type",
        }

        incidents = test_client.get("/api/v1/incidents").json()
        assert incidents["total"] == 1  # unchanged — no new detection/correlation ran

    def test_since_filter_is_accepted(self, client):
        test_client, _ = client
        self._ingest_brute_force(test_client)
        self._run_pipeline_and_wait(test_client)

        job = self._reanalyze_and_wait(test_client, {"since": "2026-01-16T00:00:00Z"})
        assert job["status"] == "completed"
        assert job["result"]["incidents_processed"] == 0

    def test_reanalyze_with_no_incidents_is_a_no_op(self, client):
        test_client, _ = client
        job = self._reanalyze_and_wait(test_client)
        assert job["status"] == "completed"
        assert job["result"]["incidents_processed"] == 0
