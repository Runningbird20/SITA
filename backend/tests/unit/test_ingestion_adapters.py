import pytest

from app.ingestion.auth import AuthIngestionAdapter
from app.ingestion.base import IngestionValidationError
from app.ingestion.dns import DNSIngestionAdapter
from app.ingestion.endpoint import EndpointIngestionAdapter
from app.ingestion.network import NetworkIngestionAdapter
from app.ingestion.web import WebIngestionAdapter
from app.models.enums import SourceType


class TestAuthAdapter:
    def test_valid_record_parses(self):
        raw = {
            "timestamp": "2026-01-15T03:10:00Z",
            "host": "web01.internal",
            "event_result": "failure",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
            "service": "sshd",
        }
        parsed = AuthIngestionAdapter().parse(raw)
        assert parsed.source_type == SourceType.AUTH
        assert parsed.source_host == "web01.internal"
        assert parsed.normalized == {
            "event_result": "failure",
            "username": "root",
            "source_ip": "203.0.113.7",
            "dest_host": "web01.internal",
            "auth_method": "password",
        }
        assert parsed.raw_payload == raw

    def test_missing_required_field_rejected(self):
        raw = {
            "timestamp": "2026-01-15T03:10:00Z",
            "host": "web01.internal",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
        }
        with pytest.raises(IngestionValidationError) as exc_info:
            AuthIngestionAdapter().parse(raw)
        assert exc_info.value.field == "event_result"

    def test_invalid_enum_value_rejected(self):
        raw = {
            "timestamp": "2026-01-15T03:10:00Z",
            "host": "web01.internal",
            "event_result": "maybe",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
        }
        with pytest.raises(IngestionValidationError) as exc_info:
            AuthIngestionAdapter().parse(raw)
        assert exc_info.value.field == "event_result"

    def test_missing_timestamp_rejected(self):
        raw = {
            "host": "web01.internal",
            "event_result": "success",
            "username": "root",
            "source_ip": "203.0.113.7",
            "auth_method": "password",
        }
        with pytest.raises(IngestionValidationError) as exc_info:
            AuthIngestionAdapter().parse(raw)
        assert exc_info.value.field == "timestamp"


class TestEndpointAdapter:
    def test_valid_record_parses_with_optional_fields(self):
        raw = {
            "timestamp": "2026-01-15T03:18:10Z",
            "host": "ws-07.internal",
            "process_name": "powershell.exe",
            "command_line": "powershell -enc SQBFAFgA",
            "pid": 6112,
            "parent_pid": 6100,
            "parent_process_name": "cmd.exe",
            "user": "svc-web",
        }
        parsed = EndpointIngestionAdapter().parse(raw)
        assert parsed.normalized["pid"] == 6112
        assert parsed.normalized["parent_pid"] == 6100
        assert parsed.normalized["parent_process_name"] == "cmd.exe"

    def test_optional_fields_omitted_when_absent(self):
        raw = {
            "timestamp": "2026-01-15T03:18:10Z",
            "host": "ws-07.internal",
            "process_name": "notepad.exe",
            "command_line": "notepad.exe",
            "pid": 100,
            "user": "jdoe",
        }
        parsed = EndpointIngestionAdapter().parse(raw)
        assert "parent_pid" not in parsed.normalized
        assert "parent_process_name" not in parsed.normalized

    def test_wrong_type_for_pid_rejected(self):
        raw = {
            "timestamp": "2026-01-15T03:18:10Z",
            "host": "ws-07.internal",
            "process_name": "notepad.exe",
            "command_line": "notepad.exe",
            "pid": "not-a-number",
            "user": "jdoe",
        }
        with pytest.raises(IngestionValidationError) as exc_info:
            EndpointIngestionAdapter().parse(raw)
        assert exc_info.value.field == "pid"


class TestNetworkAdapter:
    def test_valid_record_parses(self):
        raw = {
            "timestamp": "2026-01-15T03:16:00Z",
            "host": "fw01.internal",
            "src_ip": "10.0.0.5",
            "src_port": 44001,
            "dst_ip": "10.0.0.7",
            "dst_port": 22,
            "protocol": "tcp",
            "bytes_sent": 40,
            "bytes_received": 0,
        }
        parsed = NetworkIngestionAdapter().parse(raw)
        assert parsed.normalized["protocol"] == "tcp"
        assert parsed.normalized["dst_port"] == 22

    def test_invalid_protocol_rejected(self):
        raw = {
            "timestamp": "2026-01-15T03:16:00Z",
            "host": "fw01.internal",
            "src_ip": "10.0.0.5",
            "src_port": 44001,
            "dst_ip": "10.0.0.7",
            "dst_port": 22,
            "protocol": "sctp",
        }
        with pytest.raises(IngestionValidationError) as exc_info:
            NetworkIngestionAdapter().parse(raw)
        assert exc_info.value.field == "protocol"


class TestDNSAdapter:
    def test_valid_record_parses(self):
        raw = {
            "timestamp": "2026-01-15T03:18:38Z",
            "host": "dns01.internal",
            "query_name": "cdn-update-service.example",
            "query_type": "TXT",
            "response_code": "NOERROR",
            "resolved_ips": ["198.51.100.77"],
            "resolver_ip": "10.0.0.2",
        }
        parsed = DNSIngestionAdapter().parse(raw)
        assert parsed.normalized["query_type"] == "TXT"
        assert parsed.normalized["resolved_ips"] == ["198.51.100.77"]

    def test_nxdomain_without_resolved_ips_parses(self):
        raw = {
            "timestamp": "2026-01-15T03:18:30Z",
            "host": "dns01.internal",
            "query_name": "qp8vn3zxrl4t.example",
            "query_type": "A",
            "response_code": "NXDOMAIN",
            "resolver_ip": "10.0.0.2",
        }
        parsed = DNSIngestionAdapter().parse(raw)
        assert "resolved_ips" not in parsed.normalized

    def test_resolved_ips_wrong_type_rejected(self):
        raw = {
            "timestamp": "2026-01-15T03:18:30Z",
            "host": "dns01.internal",
            "query_name": "example.com",
            "query_type": "A",
            "response_code": "NOERROR",
            "resolved_ips": "198.51.100.77",
            "resolver_ip": "10.0.0.2",
        }
        with pytest.raises(IngestionValidationError) as exc_info:
            DNSIngestionAdapter().parse(raw)
        assert exc_info.value.field == "resolved_ips"


class TestWebAdapter:
    def test_valid_record_parses(self):
        raw = {
            "timestamp": "2026-01-15T07:00:01Z",
            "host": "web01.internal",
            "method": "GET",
            "path": "/admin/login.php",
            "status_code": 401,
            "source_ip": "203.0.113.7",
            "user_agent": "sqlmap/1.7.11#stable",
        }
        parsed = WebIngestionAdapter().parse(raw)
        assert parsed.normalized["status_code"] == 401
        assert parsed.normalized["host"] == "web01.internal"

    def test_invalid_method_rejected(self):
        raw = {
            "timestamp": "2026-01-15T07:00:01Z",
            "host": "web01.internal",
            "method": "TRACE",
            "path": "/",
            "status_code": 200,
            "source_ip": "10.0.0.1",
        }
        with pytest.raises(IngestionValidationError) as exc_info:
            WebIngestionAdapter().parse(raw)
        assert exc_info.value.field == "method"
