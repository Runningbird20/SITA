"""Extracts host-entity candidates from a SecurityEvent. See DEF.md § Phase 5."""

import ipaddress
from typing import TYPE_CHECKING

from app.correlation.host_identity import canonical_host
from app.models.enums import EntityRole, SourceType

if TYPE_CHECKING:
    from app.models.event import SecurityEvent

# RFC 1918 (IPv4) / RFC 4193 ULA (IPv6) internal ranges specifically —
# deliberately narrower than ipaddress's own `.is_private`, which also
# flags RFC 5737 documentation ranges (203.0.113.0/24, 198.51.100.0/24,
# 192.0.2.0/24) as private. This project uses those documentation ranges
# throughout its synthetic datasets to represent *external* attacker
# addresses (the same RFC-reserved-range convention as Phase 4's `.example`
# domains) — trusting `.is_private` here would wrongly treat attacker
# infrastructure as "our" host entities.
_INTERNAL_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
]


def _is_internal(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(addr in network for network in _INTERNAL_NETWORKS if addr.version == network.version)


def extract_host_candidates(event: "SecurityEvent") -> list[tuple[str, EntityRole]]:
    """Returns (canonical_identifier, role) pairs for the host(s) this
    event is associated with.

    `network` events involve two hosts (source and destination), restricted
    to private/internal addresses — a public address there is attacker
    infrastructure, already covered as an IOC, not "our" host. Every other
    source type uses SecurityEvent.source_host directly (universally
    populated by every ingestion adapter), not a per-source `normalized`
    field — `endpoint`'s normalized shape has no host key at all.
    """
    if event.source_type == SourceType.NETWORK:
        candidates: list[tuple[str, EntityRole]] = []
        for field, role in (("src_ip", EntityRole.SOURCE), ("dst_ip", EntityRole.TARGET)):
            value = event.normalized.get(field)
            if not value:
                continue
            try:
                addr = ipaddress.ip_address(value)
            except ValueError:
                continue
            if _is_internal(addr):
                candidates.append((canonical_host(value), role))
        return candidates

    if event.source_host:
        return [(canonical_host(event.source_host), EntityRole.SOURCE)]
    return []
