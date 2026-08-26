"""Runs the real evaluation harness against the real checked-in data/eval/
dataset and locks in the result — a regression test, not a fixture-based
unit test, since the whole point is exercising the actual held-out dataset
against the actual pipeline. See DEF.md § Phase 12.
"""

from app.evaluation.harness import run_evaluation


class TestEvaluationHarness:
    def test_perfect_score_against_the_real_eval_dataset(self, db_session):
        report = run_evaluation(db_session)

        assert report.detection_overall.precision == 1.0
        assert report.detection_overall.recall == 1.0
        for rule, counts in report.detection_by_rule.items():
            assert counts.precision == 1.0, f"{rule} precision regressed"
            assert counts.recall == 1.0, f"{rule} recall regressed"

        assert report.ioc_overall.precision == 1.0
        assert report.ioc_overall.recall == 1.0
        for ioc_type, counts in report.ioc_by_type.items():
            assert counts.precision in (1.0, None), f"{ioc_type} precision regressed"
            assert counts.recall == 1.0, f"{ioc_type} recall regressed"

        assert report.correlation_accuracy == 1.0
        assert report.correlation_failures == []

    def test_every_detection_rule_is_represented(self, db_session):
        report = run_evaluation(db_session)
        expected_rules = {
            "ssh_brute_force",
            "password_spraying",
            "suspicious_auth_pattern",
            "repeated_auth_failures",
            "port_scanning",
            "suspicious_powershell",
            "impossible_travel",
        }
        assert expected_rules <= set(report.detection_by_rule.keys())

    def test_every_ioc_type_is_represented(self, db_session):
        report = run_evaluation(db_session)
        expected_types = {
            "ipv4",
            "ipv6",
            "domain",
            "url",
            "email",
            "file_hash_md5",
            "file_hash_sha1",
            "file_hash_sha256",
            "username",
        }
        assert expected_types <= set(report.ioc_by_type.keys())
