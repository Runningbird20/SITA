from datetime import UTC, datetime

from app.correlation.host_extraction import extract_host_candidates
from app.models.enums import EntityRole, SourceType

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


class _FakeEvent:
    def __init__(self, source_type, normalized, source_host=None):
        self.source_type = source_type
        self.normalized = normalized
        self.source_host = source_host


class TestExtractHostCandidates:
    def test_auth_event_uses_source_host(self):
        event = _FakeEvent(
            SourceType.AUTH, {"dest_host": "web01.internal"}, source_host="web01.internal"
        )
        candidates = extract_host_candidates(event)
        assert candidates == [("web01.internal", EntityRole.SOURCE)]

    def test_network_event_yields_both_private_endpoints(self):
        event = _FakeEvent(
            SourceType.NETWORK,
            {"src_ip": "10.0.0.20", "dst_ip": "10.0.0.30"},
        )
        candidates = extract_host_candidates(event)
        assert ("10.0.0.20", EntityRole.SOURCE) in candidates
        assert ("10.0.0.30", EntityRole.TARGET) in candidates
        assert len(candidates) == 2

    def test_network_event_filters_public_addresses(self):
        event = _FakeEvent(
            SourceType.NETWORK,
            {"src_ip": "10.0.0.20", "dst_ip": "203.0.113.7"},
        )
        candidates = extract_host_candidates(event)
        assert candidates == [("10.0.0.20", EntityRole.SOURCE)]

    def test_network_event_applies_known_alias(self):
        event = _FakeEvent(SourceType.NETWORK, {"src_ip": "10.0.0.5", "dst_ip": "10.0.0.7"})
        candidates = extract_host_candidates(event)
        assert ("web01.internal", EntityRole.SOURCE) in candidates
        assert ("ws-07.internal", EntityRole.TARGET) in candidates

    def test_event_with_no_host_yields_nothing(self):
        event = _FakeEvent(SourceType.DNS, {"query_name": "example.com"}, source_host=None)
        assert extract_host_candidates(event) == []
