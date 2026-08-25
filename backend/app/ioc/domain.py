import re

from app.ioc.base import NON_TLD_FILE_EXTENSIONS, RESERVED_TLDS, ExtractedIOC
from app.models.enums import ExtractionSource, IOCType, ValidationStatus

_LABEL = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
_PATTERN = re.compile(rf"\b(?:{_LABEL}\.)+[a-zA-Z]{{2,24}}\b")

_SCAN_CONFIDENCE = 0.6


def _is_reserved(value: str) -> bool:
    tld = value.rsplit(".", 1)[-1].lower()
    return tld in RESERVED_TLDS


def _looks_like_a_filename(value: str) -> bool:
    extension = value.rsplit(".", 1)[-1].lower()
    return extension in NON_TLD_FILE_EXTENSIONS


def scan(text: str) -> list[ExtractedIOC]:
    found: list[ExtractedIOC] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text):
        value = match.group(0).lower()
        if value in seen or _is_reserved(value) or _looks_like_a_filename(value):
            continue
        seen.add(value)
        found.append(
            ExtractedIOC(
                ioc_type=IOCType.DOMAIN,
                value=value,
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=_SCAN_CONFIDENCE,
            )
        )
    return found


def from_field(value: str) -> ExtractedIOC | None:
    normalized = value.lower().strip()
    if not _PATTERN.fullmatch(normalized):
        return None
    validation_status = (
        ValidationStatus.INVALID if _is_reserved(normalized) else ValidationStatus.VALID
    )
    return ExtractedIOC(
        ioc_type=IOCType.DOMAIN,
        value=normalized,
        extraction_source=ExtractionSource.REGEX,
        validation_status=validation_status,
        confidence=1.0,
    )
