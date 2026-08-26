from pydantic import BaseModel, ValidationError

from app.models.enums import AnalysisValidationStatus


def _dedupe_list_fields(data: dict) -> dict:
    """Small local models occasionally degenerate into repeating the same
    list item verbatim (e.g. the same investigation hypothesis 9 times in a
    row). Collapsing exact duplicates here is a deterministic cleanup of the
    *parsed* output, not a trust decision about content — the verbatim
    completion is still preserved unmodified in AnalysisResult.raw_output.
    """
    cleaned = dict(data)
    for key, value in data.items():
        if isinstance(value, list):
            deduped = []
            for item in value:
                if item not in deduped:
                    deduped.append(item)
            cleaned[key] = deduped
    return cleaned


def validate_structured_output(
    raw_text: str, schema: type[BaseModel]
) -> tuple[dict | None, AnalysisValidationStatus, str | None]:
    """Pydantic v2's model_validate_json raises ValidationError for both
    malformed JSON and schema mismatches — one exception type covers both
    failure modes this needs to report as `invalid`.
    """
    try:
        instance = schema.model_validate_json(raw_text)
    except ValidationError as exc:
        return None, AnalysisValidationStatus.INVALID, str(exc)
    parsed = _dedupe_list_fields(instance.model_dump(mode="json"))
    return parsed, AnalysisValidationStatus.VALID, None
