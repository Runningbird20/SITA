"""Direct, precise tests of score_severity()'s arithmetic — added
alongside a mutation-testing pass (see DEF.md § Phase 11, "Post-roadmap
addition: mutation testing") that found this function was previously only
exercised *indirectly* through detection-rule tests checking categorical
severity ("HIGH", "CRITICAL"), never its actual numeric formula. A wrong
constant (e.g. the volume_factor ceiling silently raised from 0.3 to 1.3)
can still land in the same severity bucket as the correct value for the
matched_count/threshold ratios those rule tests happened to use — these
tests check the exact numbers instead.
"""

from app.detection.base import score_severity
from app.models.enums import Severity


class TestScoreSeverityWeights:
    def test_low_baseline_weight(self):
        _severity, factors = score_severity(Severity.LOW, matched_count=1, threshold=100)
        assert factors["rule_weight"] == 0.25

    def test_medium_baseline_weight(self):
        _severity, factors = score_severity(Severity.MEDIUM, matched_count=1, threshold=100)
        assert factors["rule_weight"] == 0.5

    def test_high_baseline_weight(self):
        _severity, factors = score_severity(Severity.HIGH, matched_count=1, threshold=100)
        assert factors["rule_weight"] == 0.75

    def test_critical_baseline_weight(self):
        _severity, factors = score_severity(Severity.CRITICAL, matched_count=1, threshold=100)
        assert factors["rule_weight"] == 1.0


class TestScoreSeverityVolumeFactor:
    def test_volume_ratio_is_matched_count_divided_by_threshold(self):
        # matched_count=10, threshold=4 -> ratio 2.5 -> 0.05*2.5 = 0.125
        _severity, factors = score_severity(Severity.LOW, matched_count=10, threshold=4)
        assert factors["volume_factor"] == 0.125

    def test_at_threshold_volume_factor_is_exactly_0_05(self):
        # matched_count == threshold -> ratio 1.0 -> 0.05*1.0 = 0.05
        _severity, factors = score_severity(Severity.LOW, matched_count=5, threshold=5)
        assert factors["volume_factor"] == 0.05

    def test_volume_factor_is_capped_at_0_3_not_higher(self):
        # A huge overshoot (ratio 100) would give 0.05*100=5.0 uncapped —
        # must clamp to exactly 0.3, the real ceiling this project chose.
        _severity, factors = score_severity(Severity.LOW, matched_count=1000, threshold=1)
        assert factors["volume_factor"] == 0.3

    def test_zero_threshold_falls_back_to_ratio_one(self):
        _severity, factors = score_severity(Severity.LOW, matched_count=1, threshold=0)
        assert factors["volume_factor"] == 0.05


class TestScoreSeverityScoreAndBucket:
    def test_score_is_the_sum_of_weight_and_volume_factor(self):
        _severity, factors = score_severity(Severity.MEDIUM, matched_count=5, threshold=5)
        assert factors["score"] == 0.5 + 0.05

    def test_score_is_capped_at_1_0(self):
        # CRITICAL base (1.0) + any positive volume_factor must still clamp to 1.0.
        _severity, factors = score_severity(Severity.CRITICAL, matched_count=1000, threshold=1)
        assert factors["score"] == 1.0

    def test_score_just_below_critical_threshold_is_high(self):
        # HIGH weight 0.75 + volume_factor 0.05 (ratio=1) = 0.80 -> HIGH bucket (< 0.90).
        severity, factors = score_severity(Severity.HIGH, matched_count=5, threshold=5)
        assert factors["score"] == 0.80
        assert severity == Severity.HIGH

    def test_score_at_or_above_0_90_is_critical(self):
        # HIGH weight 0.75 + volume_factor capped at 0.3 = 1.0 -> min(1.0, 1.05) -> CRITICAL.
        severity, _factors = score_severity(Severity.HIGH, matched_count=1000, threshold=1)
        assert severity == Severity.CRITICAL

    def test_score_at_or_above_0_70_below_0_90_is_high(self):
        severity, factors = score_severity(Severity.MEDIUM, matched_count=1000, threshold=1)
        assert factors["score"] == 0.8  # 0.5 + 0.3 (capped)
        assert severity == Severity.HIGH

    def test_score_at_or_above_0_45_below_0_70_is_medium(self):
        severity, factors = score_severity(Severity.LOW, matched_count=1000, threshold=1)
        assert factors["score"] == 0.55  # 0.25 + 0.3 (capped)
        assert severity == Severity.MEDIUM

    def test_score_below_0_45_is_low(self):
        severity, factors = score_severity(Severity.LOW, matched_count=1, threshold=100)
        assert factors["score"] == 0.25 + 0.05 * (1 / 100)
        assert severity == Severity.LOW

    def test_asset_sensitivity_is_the_reserved_zero_placeholder(self):
        _severity, factors = score_severity(Severity.LOW, matched_count=1, threshold=1)
        assert factors["asset_sensitivity"] == 0.0

    def test_score_of_exactly_0_90_is_critical_not_high(self):
        # HIGH weight 0.75 + volume_factor 0.15 (ratio=3) = 0.90 exactly —
        # the >= 0.90 boundary itself, not just a value safely above it.
        severity, factors = score_severity(Severity.HIGH, matched_count=6, threshold=2)
        assert factors["score"] == 0.90
        assert severity == Severity.CRITICAL

    def test_score_of_exactly_0_70_is_high_not_medium(self):
        # MEDIUM weight 0.5 + volume_factor 0.20 (ratio=4) = 0.70 exactly.
        severity, factors = score_severity(Severity.MEDIUM, matched_count=8, threshold=2)
        assert factors["score"] == 0.70
        assert severity == Severity.HIGH

    def test_score_of_exactly_0_45_is_medium_not_low(self):
        # LOW weight 0.25 + volume_factor 0.20 (ratio=4) = 0.45 exactly.
        severity, factors = score_severity(Severity.LOW, matched_count=8, threshold=2)
        assert factors["score"] == 0.45
        assert severity == Severity.MEDIUM
