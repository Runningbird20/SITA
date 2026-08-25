import re

from app.ioc.base import ExtractedIOC
from app.models.enums import ExtractionSource, IOCType, ValidationStatus

_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}\b")

_CONFIDENCE = 0.85


def scan(text: str) -> list[ExtractedIOC]:
    found: list[ExtractedIOC] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text):
        value = match.group(0).lower()
        domain_part = value.rsplit("@", 1)[-1]
        if "." not in domain_part or value in seen:
            continue
        seen.add(value)
        found.append(
            ExtractedIOC(
                ioc_type=IOCType.EMAIL,
                value=value,
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=_CONFIDENCE,
            )
        )
    return found
