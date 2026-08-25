from pydantic import BaseModel, ValidationError

from app.models.enums import AnalysisValidationStatus


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
    return instance.model_dump(mode="json"), AnalysisValidationStatus.VALID, None
