from datetime import UTC, datetime, timedelta

from app.detection.anomalous_volume import AnomalousEventVolumeRule
from app.detection.dns_tunneling import DNSTunnelingRule
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


class TestDNSTunneling:
    def _dns_event(
        self,
        make_event,
        offset_seconds,
        query_name,
        response_code="NOERROR",
        resolver_ip="10.0.0.2",
        query_type="A",
    ):
        return make_event(
            SourceType.DNS,
            NOW + timedelta(seconds=offset_seconds),
            {
                "query_name": query_name,
                "query_type": query_type,
                "response_code": response_code,
                "resolver_ip": resolver_ip,
            },
        )

    def test_dga_style_cycling_under_shared_suffix_triggers(self, db_session, make_event):
        # Mirrors data/synthetic_events/dns/suspicious_domain.jsonl: a couple
        # of NXDOMAIN lookups against random-looking candidate names, then a
        # resolved name queried for TXT (a classic DNS C2 exfil pattern),
        # all sharing the ".example" pseudo-TLD.
        events = [
            self._dns_event(make_event, 0, "xk29fh3mdq7z.example", response_code="NXDOMAIN"),
            self._dns_event(make_event, 15, "b7q1lz9wpm2a.example", response_code="NXDOMAIN"),
            self._dns_event(make_event, 30, "cdn-update-service.example", query_type="TXT"),
        ]
        findings = DNSTunnelingRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert len(findings[0].matched_event_ids) == 3
        assert findings[0].severity_factors["nxdomain_ratio"] > 0

    def test_ordinary_multi_domain_browsing_does_not_trigger(self, db_session, make_event):
        # Several distinct, real, low-entropy SLDs sharing a real public
        # TLD (.com) within one window — the exact shape the suffix-level
        # grouping deliberately relies on the entropy/NXDOMAIN gate to keep
        # safe, since it pools all of these into one group.
        events = [
            self._dns_event(make_event, 0, "google.com"),
            self._dns_event(make_event, 5, "github.com"),
            self._dns_event(make_event, 10, "slack.com"),
        ]
        findings = DNSTunnelingRule().evaluate(db_session, events, {})
        assert findings == []

    def test_below_distinct_name_threshold_does_not_trigger(self, db_session, make_event):
        events = [
            self._dns_event(make_event, 0, "xk29fh3mdq7z.example", response_code="NXDOMAIN"),
            self._dns_event(make_event, 15, "b7q1lz9wpm2a.example", response_code="NXDOMAIN"),
        ]
        findings = DNSTunnelingRule().evaluate(db_session, events, {})
        assert findings == []

    def test_high_entropy_without_nxdomain_still_triggers(self, db_session, make_event):
        # All resolve successfully (no NXDOMAIN signal), but the labels are
        # random-looking enough on their own to cross the entropy gate.
        events = [
            self._dns_event(make_event, 0, "xk29fh3mdq7z.example"),
            self._dns_event(make_event, 15, "b7q1lz9wpm2a.example"),
            self._dns_event(make_event, 30, "mq0zxv8ktn5r.example"),
        ]
        findings = DNSTunnelingRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert findings[0].severity_factors["nxdomain_ratio"] == 0
        assert findings[0].severity_factors["avg_label_entropy"] > 0

    def test_different_resolvers_are_not_merged(self, db_session, make_event):
        events = [
            self._dns_event(
                make_event,
                0,
                "xk29fh3mdq7z.example",
                response_code="NXDOMAIN",
                resolver_ip="10.0.0.2",
            ),
            self._dns_event(
                make_event,
                15,
                "b7q1lz9wpm2a.example",
                response_code="NXDOMAIN",
                resolver_ip="10.0.0.3",
            ),
            self._dns_event(
                make_event,
                30,
                "mq0zxv8ktn5r.example",
                response_code="NXDOMAIN",
                resolver_ip="10.0.0.4",
            ),
        ]
        findings = DNSTunnelingRule().evaluate(db_session, events, {})
        assert findings == []


class TestAnomalousEventVolume:
    def _day_events(self, make_event, host, day_offset, count):
        day = NOW.replace(hour=8, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
        return [
            make_event(
                SourceType.ENDPOINT,
                day + timedelta(minutes=i * 3),
                {
                    "process_name": "explorer.exe",
                    "command_line": "C:\\Windows\\explorer.exe",
                    "pid": 1000 + i,
                    "user": "jrivera",
                },
                host=host,
            )
            for i in range(count)
        ]

    def test_volume_spike_after_baseline_triggers(self, db_session, make_event):
        events = []
        for day_offset, count in enumerate([5, 4, 6, 5, 4]):
            events += self._day_events(make_event, "ws-20.internal", day_offset, count)
        events += self._day_events(make_event, "ws-20.internal", 5, 25)

        findings = AnomalousEventVolumeRule().evaluate(db_session, events, {})
        assert len(findings) == 1
        assert len(findings[0].matched_event_ids) == 25
        assert findings[0].severity_factors["baseline_days"] == 5

    def test_normal_day_within_baseline_does_not_trigger(self, db_session, make_event):
        events = []
        for day_offset, count in enumerate([5, 4, 6, 5, 4]):
            events += self._day_events(make_event, "ws-21.internal", day_offset, count)
        # One more ordinary day, same shape as the baseline itself.
        events += self._day_events(make_event, "ws-21.internal", 5, 5)

        findings = AnomalousEventVolumeRule().evaluate(db_session, events, {})
        assert findings == []

    def test_insufficient_baseline_history_does_not_trigger(self, db_session, make_event):
        events = []
        # Only 2 prior days — below the default min_baseline_days of 3 —
        # even though the following day is a huge, genuine spike.
        for day_offset, count in enumerate([5, 4]):
            events += self._day_events(make_event, "ws-22.internal", day_offset, count)
        events += self._day_events(make_event, "ws-22.internal", 2, 30)

        findings = AnomalousEventVolumeRule().evaluate(db_session, events, {})
        assert findings == []

    def test_below_min_current_day_count_does_not_trigger(self, db_session, make_event):
        events = []
        # A steady 1-event/day baseline, then a day with only 3 events —
        # statistically anomalous (z-score comfortably over threshold) but
        # too small in absolute terms to be worth an alert.
        for day_offset in range(4):
            events += self._day_events(make_event, "ws-23.internal", day_offset, 1)
        events += self._day_events(make_event, "ws-23.internal", 4, 3)

        findings = AnomalousEventVolumeRule().evaluate(db_session, events, {})
        assert findings == []

    def test_different_hosts_do_not_share_a_baseline(self, db_session, make_event):
        events = []
        for day_offset, count in enumerate([5, 4, 6, 5, 4]):
            events += self._day_events(make_event, "ws-24.internal", day_offset, count)
        # A second host with only one day of history and a large count —
        # its own insufficient baseline must not borrow ws-24's.
        events += self._day_events(make_event, "ws-25.internal", 5, 25)

        findings = AnomalousEventVolumeRule().evaluate(db_session, events, {})
        assert findings == []
