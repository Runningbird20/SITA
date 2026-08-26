from pydantic import BaseModel

from app.llm.validation import validate_structured_output
from app.models.enums import AnalysisValidationStatus


class _ExampleSchema(BaseModel):
    """Illustrative schema for Phase 6's own tests — not a real Phase 7
    task schema."""

    summary: str
    confidence_label: str


class _ListFieldSchema(BaseModel):
    hypotheses: list[str]
    steps: list[dict]


class TestValidateStructuredOutput:
    def test_valid_json_matching_schema(self):
        parsed, status, error = validate_structured_output(
            '{"summary": "brute force detected", "confidence_label": "high"}', _ExampleSchema
        )
        assert status == AnalysisValidationStatus.VALID
        assert parsed == {"summary": "brute force detected", "confidence_label": "high"}
        assert error is None

    def test_malformed_json(self):
        parsed, status, error = validate_structured_output("not json at all", _ExampleSchema)
        assert status == AnalysisValidationStatus.INVALID
        assert parsed is None
        assert error is not None

    def test_valid_json_missing_required_field(self):
        parsed, status, error = validate_structured_output(
            '{"summary": "brute force detected"}', _ExampleSchema
        )
        assert status == AnalysisValidationStatus.INVALID
        assert parsed is None
        assert "confidence_label" in error

    def test_valid_json_wrong_type(self):
        parsed, status, error = validate_structured_output(
            '{"summary": 123, "confidence_label": "high"}', _ExampleSchema
        )
        assert status == AnalysisValidationStatus.INVALID
        assert parsed is None

    def test_extra_fields_are_ignored_by_default_pydantic_behavior(self):
        parsed, status, error = validate_structured_output(
            '{"summary": "x", "confidence_label": "high", "extra": "field"}', _ExampleSchema
        )
        assert status == AnalysisValidationStatus.VALID
        assert "extra" not in parsed

    def test_exact_duplicate_list_items_are_collapsed(self):
        raw = (
            '{"hypotheses": ["same hypothesis", "same hypothesis", "same hypothesis"], '
            '"steps": [{"text": "check logs", "priority": "high"}, '
            '{"text": "check logs", "priority": "high"}]}'
        )
        parsed, status, error = validate_structured_output(raw, _ListFieldSchema)
        assert status == AnalysisValidationStatus.VALID
        assert parsed["hypotheses"] == ["same hypothesis"]
        assert parsed["steps"] == [{"text": "check logs", "priority": "high"}]

    def test_distinct_list_items_are_preserved_in_order(self):
        raw = '{"hypotheses": ["first", "second", "first"], "steps": []}'
        parsed, status, error = validate_structured_output(raw, _ListFieldSchema)
        assert status == AnalysisValidationStatus.VALID
        assert parsed["hypotheses"] == ["first", "second"]
