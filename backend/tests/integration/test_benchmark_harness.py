"""Smoke test for the performance benchmark harness — benchmarks are about
real timing, not correctness assertions, so this only confirms the harness
runs end-to-end against a small load and returns well-formed data, not any
particular throughput/latency number. See DEF.md § Phase 12.
"""

from app.benchmark.harness import run_benchmark


class TestBenchmarkHarness:
    def test_runs_end_to_end_and_returns_well_formed_report(self):
        report = run_benchmark(events_per_source=20, api_requests=3)

        stage_labels = {s.label for s in report.stages}
        assert stage_labels == {
            "ingestion",
            "detection",
            "ioc_extraction",
            "mitre_mapping",
            "correlation",
            "triage_orchestration_mock",
        }
        for stage in report.stages:
            assert stage.seconds >= 0
            assert stage.unit_count > 0

        api_labels = {a.label for a in report.api_latencies}
        assert api_labels == {
            "GET /incidents (list)",
            "GET /alerts (list)",
            "GET /iocs (search)",
        }
        for latencies in report.api_latencies:
            assert latencies.samples_ms
            assert len(latencies.samples_ms) == 3

        assert report.triage_mock_latency_ms is not None
        assert report.triage_mock_latency_ms >= 0
