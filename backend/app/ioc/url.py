import re
from urllib.parse import urlparse

from app.ioc.base import ExtractedIOC
from app.models.enums import ExtractionSource, IOCType, ValidationStatus

_PATTERN = re.compile(r"\b(?:https?|ftp)://[^\s'\"()<>]+", re.IGNORECASE)

_CONFIDENCE = 0.85


def scan(text: str) -> list[ExtractedIOC]:
    found: list[ExtractedIOC] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text):
        value = match.group(0).rstrip(").,;")
        if value in seen:
            continue
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            continue
        seen.add(value)
        found.append(
            ExtractedIOC(
                ioc_type=IOCType.URL,
                value=value,
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=_CONFIDENCE,
            )
        )
    return found
