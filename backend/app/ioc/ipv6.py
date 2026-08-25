import ipaddress
import re

from app.ioc.base import ExtractedIOC
from app.models.enums import ExtractionSource, IOCType, ValidationStatus

# Deliberately permissive — full RFC 4291 compliance is validated by
# ipaddress.IPv6Address, not the regex. This just finds plausible candidates
# (hex groups separated by colons, allowing the "::" compression form).
_PATTERN = re.compile(r"\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")

_CONFIDENCE = 0.7


def scan(text: str) -> list[ExtractedIOC]:
    found: list[ExtractedIOC] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text):
        value = match.group(0)
        if value in seen or value.count(":") < 2:
            continue
        try:
            addr = ipaddress.IPv6Address(value)
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            continue
        seen.add(value)
        found.append(
            ExtractedIOC(
                ioc_type=IOCType.IPV6,
                value=value,
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=_CONFIDENCE,
            )
        )
    return found


def from_field(value: str) -> ExtractedIOC | None:
    try:
        ipaddress.IPv6Address(value)
    except ValueError:
        return None
    return ExtractedIOC(
        ioc_type=IOCType.IPV6,
        value=value,
        extraction_source=ExtractionSource.REGEX,
        validation_status=ValidationStatus.VALID,
        confidence=1.0,
    )
