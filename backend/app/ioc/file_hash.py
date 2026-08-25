import re

from app.ioc.base import ExtractedIOC
from app.models.enums import ExtractionSource, IOCType, ValidationStatus

_PATTERN = re.compile(r"\b[0-9a-fA-F]{32,64}\b")

_TYPE_BY_LENGTH = {
    32: IOCType.FILE_HASH_MD5,
    40: IOCType.FILE_HASH_SHA1,
    64: IOCType.FILE_HASH_SHA256,
}

_CONFIDENCE = 0.9


def scan(text: str) -> list[ExtractedIOC]:
    found: list[ExtractedIOC] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text):
        value = match.group(0).lower()
        ioc_type = _TYPE_BY_LENGTH.get(len(value))
        if ioc_type is None or value in seen:
            continue
        seen.add(value)
        found.append(
            ExtractedIOC(
                ioc_type=ioc_type,
                value=value,
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=_CONFIDENCE,
            )
        )
    return found
