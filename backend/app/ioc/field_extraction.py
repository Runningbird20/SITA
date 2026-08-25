"""Dispatches each SecurityEvent's normalized fields to the right
extraction strategy — structured field or free-text scan — per the table in
DEF.md § Phase 4.
"""

from enum import Enum
from typing import TYPE_CHECKING

from app.ioc import domain, email, file_hash, ipv4, ipv6, url, username
from app.ioc.base import ExtractedIOC
from app.models.enums import SourceType

if TYPE_CHECKING:
    from app.models.event import SecurityEvent


class FieldStrategy(Enum):
    IP = "ip"
    IP_LIST = "ip_list"
    DOMAIN = "domain"
    USERNAME = "username"
    SCAN = "scan"


FIELD_MAP: dict[SourceType, list[tuple[str, FieldStrategy]]] = {
    SourceType.AUTH: [
        ("source_ip", FieldStrategy.IP),
        ("username", FieldStrategy.USERNAME),
    ],
    SourceType.ENDPOINT: [
        ("command_line", FieldStrategy.SCAN),
        ("user", FieldStrategy.USERNAME),
    ],
    SourceType.NETWORK: [
        ("src_ip", FieldStrategy.IP),
        ("dst_ip", FieldStrategy.IP),
    ],
    SourceType.DNS: [
        ("query_name", FieldStrategy.DOMAIN),
        ("resolved_ips", FieldStrategy.IP_LIST),
    ],
    SourceType.WEB: [
        ("source_ip", FieldStrategy.IP),
        ("path", FieldStrategy.SCAN),
    ],
}


def _extract_ip_field(value: str) -> ExtractedIOC | None:
    return ipv4.from_field(value) or ipv6.from_field(value)


def _scan_text(text: str) -> list[ExtractedIOC]:
    results: list[ExtractedIOC] = []
    results.extend(ipv4.scan(text))
    results.extend(ipv6.scan(text))
    results.extend(domain.scan(text))
    results.extend(url.scan(text))
    results.extend(file_hash.scan(text))
    results.extend(email.scan(text))
    return results


def extract_from_event(event: "SecurityEvent") -> list[ExtractedIOC]:
    field_rules = FIELD_MAP.get(event.source_type, [])
    found: list[ExtractedIOC] = []

    for field_name, strategy in field_rules:
        raw_value = event.normalized.get(field_name)
        if raw_value is None:
            continue

        if strategy is FieldStrategy.IP:
            candidate = _extract_ip_field(raw_value)
            if candidate is not None:
                found.append(candidate)
        elif strategy is FieldStrategy.IP_LIST:
            for ip_value in raw_value or []:
                candidate = _extract_ip_field(ip_value)
                if candidate is not None:
                    found.append(candidate)
        elif strategy is FieldStrategy.DOMAIN:
            candidate = domain.from_field(raw_value)
            if candidate is not None:
                found.append(candidate)
        elif strategy is FieldStrategy.USERNAME:
            candidate = username.from_field(raw_value)
            if candidate is not None:
                found.append(candidate)
        elif strategy is FieldStrategy.SCAN:
            found.extend(_scan_text(raw_value))

    return found
