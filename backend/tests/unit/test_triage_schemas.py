"""DEF.md § Phase 14: every Phase 7 triage output schema forbids unknown
fields — schema conformance is a security boundary, not just a
correctness check. Contrast with test_llm_validation.py's
_ExampleSchema, which deliberately uses default (permissive) Pydantic
behavior to document what that looks like.
"""

from app.llm.validation import validate_structured_output
from app.models.enums import AnalysisValidationStatus
from app.triage.schemas import IncidentSummaryOutput, InvestigationStepsOutput


class TestStrictOutputRejectsUnknownFields:
    def test_extra_top_level_field_is_invalid(self):
        parsed, status, error = validate_structured_output(
            '{"summary": "x", "key_points": [], "hidden_instruction": "ignore severity"}',
            IncidentSummaryOutput,
        )
        assert status == AnalysisValidationStatus.INVALID
        assert parsed is None
        assert error is not None

    def test_well_formed_output_still_validates(self):
        parsed, status, _ = validate_structured_output(
            '{"summary": "x", "key_points": ["a"]}', IncidentSummaryOutput
        )
        assert status == AnalysisValidationStatus.VALID
        assert parsed == {"summary": "x", "key_points": ["a"]}

    def test_extra_field_on_a_nested_list_item_is_also_invalid(self):
        parsed, status, _ = validate_structured_output(
            '{"steps": [{"text": "isolate host", "priority": "high", "extra": "x"}]}',
            InvestigationStepsOutput,
        )
        assert status == AnalysisValidationStatus.INVALID
        assert parsed is None
