from datetime import UTC, datetime, timedelta

from app.detection.impossible_travel import ImpossibleTravelRule
from app.detection.password_spraying import PasswordSprayingRule
from app.detection.port_scanning import PortScanningRule
from app.detection.repeated_auth_failures import RepeatedAuthFailuresRule
from app.detection.ssh_brute_force import SSHBruteForceRule
from app.detection.suspicious_auth_pattern import SuspiciousAuthPatternRule
from app.detection.suspicious_powershell import SuspiciousPowerShellRule
from app.models.enums import Severity, SourceType

NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def auth_event(make_event, offset_seconds, event_result, username, source_ip, host="db01.internal"):
    return make_event(
        SourceType.AUTH,
        NOW + timedelta(seconds=offset_seconds),
        {
            "event_result": event_result,
            "username": username,
            "source_ip": source_ip,
            "dest_host": host,
            "auth_method": "password",
        },
        host=host,
    )


class TestSSHBruteForce:
    def test_threshold_failures_trigger(self, db_session, make_event):
        events = [
            auth_event(make_event, i * 20, "failure", "admin", "198.51.100.1") for i in range(10)
        ]
        findings = SSHBruteForceRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert findings[0].severity in {Severity.HIGH, Severity.CRITICAL}
        assert len(findings[0].matched_event_ids) == 10

    def test_below_threshold_does_not_trigger(self, db_session, make_event):
        events = [
            auth_event(make_event, i * 20, "failure", "admin", "198.51.100.1") for i in range(9)
        ]
        findings = SSHBruteForceRule().evaluate(db_session, events, {})
        assert findings == []

    def test_trailing_success_escalates_to_critical(self, db_session, make_event):
        events = [
            auth_event(make_event, i * 20, "failure", "admin", "198.51.100.1") for i in range(10)
        ]
        events.append(auth_event(make_event, 10 * 20 + 10, "success", "admin", "198.51.100.1"))
        findings = SSHBruteForceRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert findings[0].severity == Severity.CRITICAL
        assert len(findings[0].matched_event_ids) == 11
        assert "successful login" in findings[0].rationale

    def test_different_source_ips_do_not_combine(self, db_session, make_event):
        events = [
            auth_event(make_event, i * 20, "failure", "admin", f"198.51.100.{i}") for i in range(10)
        ]
        findings = SSHBruteForceRule().evaluate(db_session, events, {})
        assert findings == []


class TestPasswordSpraying:
    def test_many_usernames_few_attempts_triggers(self, db_session, make_event):
        events = [
            auth_event(make_event, i * 30, "failure", f"user{i}", "203.0.113.44") for i in range(5)
        ]
        findings = PasswordSprayingRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert len(findings[0].matched_event_ids) == 5

    def test_below_distinct_username_threshold_does_not_trigger(self, db_session, make_event):
        events = [
            auth_event(make_event, i * 30, "failure", f"user{i}", "203.0.113.44") for i in range(4)
        ]
        findings = PasswordSprayingRule().evaluate(db_session, events, {})
        assert findings == []

    def test_many_attempts_per_username_is_brute_force_not_spraying(self, db_session, make_event):
        events = []
        for i in range(5):
            for attempt in range(4):
                events.append(
                    auth_event(
                        make_event, i * 100 + attempt * 10, "failure", f"user{i}", "203.0.113.44"
                    )
                )
        findings = PasswordSprayingRule().evaluate(db_session, events, {})
        assert findings == []


class TestSuspiciousAuthPattern:
    def test_off_hours_login_triggers(self, db_session, make_event):
        off_hours_time = datetime(2026, 1, 15, 2, 0, 0, tzinfo=UTC)
        event = make_event(
            SourceType.AUTH,
            off_hours_time,
            {
                "event_result": "success",
                "username": "ops-admin",
                "source_ip": "10.0.0.9",
                "dest_host": "web01.internal",
                "auth_method": "mfa",
            },
        )
        findings = SuspiciousAuthPatternRule().evaluate(db_session, [event], {})
        assert len(findings) == 1
        assert "off" in findings[0].rationale.lower() or "outside" in findings[0].rationale.lower()

    def test_normal_hours_known_ip_does_not_trigger(self, db_session, make_event):
        event = make_event(
            SourceType.AUTH,
            datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            {
                "event_result": "success",
                "username": "ops-admin",
                "source_ip": "10.0.0.9",
                "dest_host": "web01.internal",
                "auth_method": "mfa",
            },
        )
        findings = SuspiciousAuthPatternRule().evaluate(db_session, [event], {})
        assert findings == []

    def test_new_ip_for_known_user_triggers(self, db_session, make_event):
        prior = make_event(
            SourceType.AUTH,
            datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            {
                "event_result": "success",
                "username": "jdoe",
                "source_ip": "10.0.0.42",
                "dest_host": "web01.internal",
                "auth_method": "publickey",
            },
        )
        new_ip_login = make_event(
            SourceType.AUTH,
            datetime(2026, 1, 15, 11, 0, 0, tzinfo=UTC),
            {
                "event_result": "success",
                "username": "jdoe",
                "source_ip": "198.51.100.201",
                "dest_host": "web01.internal",
                "auth_method": "publickey",
            },
        )
        findings = SuspiciousAuthPatternRule().evaluate(db_session, [prior, new_ip_login], {})
        assert len(findings) == 1
        assert findings[0].matched_event_ids == [new_ip_login.id]

    def test_first_ever_login_is_not_flagged_as_new_ip(self, db_session, make_event):
        first_login = make_event(
            SourceType.AUTH,
            datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC),
            {
                "event_result": "success",
                "username": "brand-new-user",
                "source_ip": "10.0.0.99",
                "dest_host": "web01.internal",
                "auth_method": "publickey",
            },
        )
        findings = SuspiciousAuthPatternRule().evaluate(db_session, [first_login], {})
        assert findings == []


class TestPortScanning:
    def _network_event(self, make_event, offset_seconds, dst_port, src_ip="198.51.100.9"):
        return make_event(
            SourceType.NETWORK,
            NOW + timedelta(seconds=offset_seconds),
            {
                "src_ip": src_ip,
                "src_port": 40000 + dst_port,
                "dst_ip": "10.0.0.5",
                "dst_port": dst_port,
                "protocol": "tcp",
            },
        )

    def test_many_distinct_ports_triggers(self, db_session, make_event):
        events = [
            self._network_event(make_event, i * 5, port)
            for i, port in enumerate([21, 22, 23, 80, 443, 3389])
        ]
        findings = PortScanningRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert len(findings[0].matched_event_ids) == 6

    def test_below_threshold_does_not_trigger(self, db_session, make_event):
        events = [
            self._network_event(make_event, i * 5, port)
            for i, port in enumerate([21, 22, 23, 80, 443])
        ]
        findings = PortScanningRule().evaluate(db_session, events, {})
        assert findings == []


class TestSuspiciousPowerShell:
    def _endpoint_event(self, make_event, process_name, command_line):
        return make_event(
            SourceType.ENDPOINT,
            NOW,
            {
                "process_name": process_name,
                "command_line": command_line,
                "pid": 1234,
                "user": "kmiller",
            },
        )

    def test_encoded_command_triggers(self, db_session, make_event):
        event = self._endpoint_event(make_event, "powershell.exe", "powershell.exe -Enc SQBFAFgA")
        findings = SuspiciousPowerShellRule().evaluate(db_session, [event], {})
        assert len(findings) == 1
        assert findings[0].confidence == 0.5

    def test_multiple_indicators_increase_confidence(self, db_session, make_event):
        event = self._endpoint_event(
            make_event,
            "powershell.exe",
            "powershell.exe -NoP -W Hidden -Exec Bypass -Enc SQBFAFgA",
        )
        findings = SuspiciousPowerShellRule().evaluate(db_session, [event], {})
        assert len(findings) == 1
        assert findings[0].confidence > 0.5
        assert len(findings[0].severity_factors["matched_categories"]) >= 3

    def test_benign_powershell_does_not_trigger(self, db_session, make_event):
        event = self._endpoint_event(make_event, "powershell.exe", "powershell.exe Get-Process")
        findings = SuspiciousPowerShellRule().evaluate(db_session, [event], {})
        assert findings == []

    def test_non_powershell_process_does_not_trigger(self, db_session, make_event):
        event = self._endpoint_event(make_event, "cmd.exe", "cmd.exe -Enc suspicious")
        findings = SuspiciousPowerShellRule().evaluate(db_session, [event], {})
        assert findings == []


class TestImpossibleTravel:
    def test_distant_locations_within_short_window_triggers(self, db_session, make_event):
        first = auth_event(make_event, 0, "success", "svc-remote", "203.0.113.7")
        second = auth_event(make_event, 8 * 60, "success", "svc-remote", "198.51.100.88")
        findings = ImpossibleTravelRule().evaluate(db_session, [first, second], {})
        assert len(findings) == 1
        assert findings[0].matched_event_ids == [first.id, second.id]

    def test_same_ip_does_not_trigger(self, db_session, make_event):
        first = auth_event(make_event, 0, "success", "svc-remote", "203.0.113.7")
        second = auth_event(make_event, 8 * 60, "success", "svc-remote", "203.0.113.7")
        findings = ImpossibleTravelRule().evaluate(db_session, [first, second], {})
        assert findings == []

    def test_unresolvable_ip_is_silently_skipped(self, db_session, make_event):
        first = auth_event(make_event, 0, "success", "svc-remote", "203.0.113.7")
        second = auth_event(make_event, 8 * 60, "success", "svc-remote", "1.2.3.4")
        findings = ImpossibleTravelRule().evaluate(db_session, [first, second], {})
        assert findings == []

    def test_plausible_travel_time_does_not_trigger(self, db_session, make_event):
        first = auth_event(make_event, 0, "success", "svc-remote", "203.0.113.7")
        second = auth_event(make_event, 20 * 3600, "success", "svc-remote", "198.51.100.88")
        findings = ImpossibleTravelRule().evaluate(db_session, [first, second], {})
        assert findings == []


class TestRepeatedAuthFailures:
    def test_distributed_failures_across_many_sources_triggers(self, db_session, make_event):
        events = []
        for i in range(20):
            events.append(
                auth_event(make_event, i * 20, "failure", "admin", f"198.51.100.{i % 4 + 10}")
            )
        findings = RepeatedAuthFailuresRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert findings[0].severity_factors["distinct_source_ips"] >= 3

    def test_single_source_does_not_trigger_this_rule(self, db_session, make_event):
        # 20 failures from ONE source IP crosses the volume threshold but not
        # the distinct-source-IP minimum — this shape belongs to
        # ssh_brute_force, not repeated_auth_failures.
        events = [
            auth_event(make_event, i * 20, "failure", "admin", "198.51.100.1") for i in range(20)
        ]
        findings = RepeatedAuthFailuresRule().evaluate(db_session, events, {})
        assert findings == []

    def test_below_volume_threshold_does_not_trigger(self, db_session, make_event):
        events = []
        for i in range(15):
            events.append(
                auth_event(make_event, i * 20, "failure", "admin", f"198.51.100.{i % 4 + 10}")
            )
        findings = RepeatedAuthFailuresRule().evaluate(db_session, events, {})
        assert findings == []
