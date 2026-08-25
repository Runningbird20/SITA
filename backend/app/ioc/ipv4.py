import ipaddress
import re

from app.ioc.base import ExtractedIOC
from app.models.enums import ExtractionSource, IOCType, ValidationStatus

_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
)

_CONFIDENCE = 0.7


def scan(text: str) -> list[ExtractedIOC]:
    """Free-text scan. Private/loopback/link-local/reserved addresses are
    filtered out — they're noise outside a structured field context. See
    DEF.md § Phase 4.
    """
    found: list[ExtractedIOC] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text):
        value = match.group(0)
        if value in seen:
            continue
        try:
            addr = ipaddress.IPv4Address(value)
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            continue
        seen.add(value)
        found.append(
            ExtractedIOC(
                ioc_type=IOCType.IPV4,
                value=value,
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=_CONFIDENCE,
            )
        )
    return found


def from_field(value: str) -> ExtractedIOC | None:
    """Structured-field strategy: trust the field, keep private/internal
    addresses (needed for correlation), still validate the format.
    """
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return None
    return ExtractedIOC(
        ioc_type=IOCType.IPV4,
        value=value,
        extraction_source=ExtractionSource.REGEX,
        validation_status=ValidationStatus.VALID,
        confidence=1.0,
    )
