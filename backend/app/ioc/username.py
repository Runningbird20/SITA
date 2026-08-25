from app.ioc.base import ExtractedIOC
from app.models.enums import ExtractionSource, IOCType, ValidationStatus


def from_field(value: str) -> ExtractedIOC | None:
    """Field-only — usernames are never regex-scanned from free text; a
    regex cannot distinguish "this word is a username" from any other word.
    """
    cleaned = value.strip()
    if not cleaned:
        return None
    return ExtractedIOC(
        ioc_type=IOCType.USERNAME,
        value=cleaned,
        extraction_source=ExtractionSource.REGEX,
        validation_status=ValidationStatus.VALID,
        confidence=1.0,
    )
