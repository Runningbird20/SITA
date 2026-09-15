"""Smoke test for the concurrent write-load stress harness — like
test_benchmark_harness.py, this is about the harness running end-to-end
and returning well-formed data, not any particular throughput number
(and the real point of this harness is exactly that failures are
expected and counted, not asserted away). See DEF.md § Phase 12,
"Post-roadmap addition: concurrent-write stress test".
"""

from app.benchmark.concurrent_load import run_concurrent_write_load
from app.core.rate_limit import reset_rate_limiters


class TestConcurrentWriteLoad:
    def test_runs_end_to_end_and_returns_well_formed_result(self):
        reset_rate_limiters()
        result = run_concurrent_write_load(
            concurrency=3, requests_per_worker=2, events_per_request=5
        )

        assert result.database == "sqlite"
        assert result.total_requests == 6
        assert result.successful_requests + result.failed_requests == result.total_requests
        assert result.total_events == result.successful_requests * 5
        assert result.wall_clock_seconds >= 0
        assert result.events_per_second >= 0

    def test_low_concurrency_single_worker_succeeds_cleanly(self):
        reset_rate_limiters()
        result = run_concurrent_write_load(
            concurrency=1, requests_per_worker=3, events_per_request=5
        )

        assert result.successful_requests == 3
        assert result.failed_requests == 0

    def test_as_dict_matches_the_dataclass_fields(self):
        reset_rate_limiters()
        result = run_concurrent_write_load(
            concurrency=1, requests_per_worker=1, events_per_request=5
        )

        body = result.as_dict()
        assert body["database"] == "sqlite"
        assert body["concurrency"] == 1
        assert body["total_requests"] == 1
