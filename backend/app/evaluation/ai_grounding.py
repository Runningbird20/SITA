"""Automated grounding checks for AI-generated triage output — resolves
TODO.md's "How to evaluate AI-generated triage" open question in favor of
automated checks over manual rubric scoring. See DEF.md § Phase 12: a
human rater isn't available in this project's actual workflow (an agentic
session, not a staffed eval team), so "manual 1-5 scoring" was never
really an option here.

Only meaningful against a real model: MockProvider's canned text isn't
grounded in any specific incident's data, so evaluating it would measure
the canned string, not the model. Callers should skip this against Mock.
"""

from dataclasses import dataclass, field

from app.mitre.rollup import IncidentTechniqueEntry
from app.models.analysis_result import AnalysisResult
from app.models.incident import Incident


@dataclass
class GroundingReport:
    text_outputs_checked: int = 0
    text_outputs_grounded: int = 0
    mitre_suggestions_checked: int = 0
    mitre_suggestions_overlapping: int = 0
    ungrounded_examples: list[str] = field(default_factory=list)

    @property
    def grounding_rate(self) -> float | None:
        return (
            self.text_outputs_grounded / self.text_outputs_checked
            if self.text_outputs_checked
            else None
        )

    @property
    def mitre_overlap_rate(self) -> float | None:
        return (
            self.mitre_suggestions_overlapping / self.mitre_suggestions_checked
            if self.mitre_suggestions_checked
            else None
        )

    def as_dict(self) -> dict:
        return {
            "text_outputs_checked": self.text_outputs_checked,
            "text_outputs_grounded": self.text_outputs_grounded,
            "grounding_rate": self.grounding_rate,
            "mitre_suggestions_checked": self.mitre_suggestions_checked,
            "mitre_suggestions_overlapping": self.mitre_suggestions_overlapping,
            "mitre_overlap_rate": self.mitre_overlap_rate,
            "ungrounded_examples": self.ungrounded_examples,
        }


def _real_identifiers(incident: Incident) -> set[str]:
    """Every real entity/IOC identifier actually present in this incident —
    what a non-hallucinating summary should be drawing from.
    """
    identifiers: set[str] = set()
    for alert in incident.alerts:
        for ioc in alert.iocs:
            identifiers.add(ioc.value.lower())
        for link in alert.entity_links:
            identifiers.add(link.entity.identifier.lower())
    return identifiers


def _mentions_a_real_identifier(text: str, identifiers: set[str]) -> bool:
    lowered = text.lower()
    return any(identifier in lowered for identifier in identifiers)


def evaluate_grounding(
    incident: Incident,
    results: list[AnalysisResult],
    mitre_rollup: list[IncidentTechniqueEntry],
) -> GroundingReport:
    report = GroundingReport()
    identifiers = _real_identifiers(incident)
    rule_technique_ids = {entry.technique_id for entry in mitre_rollup if "rule" in entry.sources}

    for result in results:
        if result.validation_status != "valid" or not result.parsed_output:
            continue

        if result.task_type == "incident_summary":
            text = str(result.parsed_output.get("summary", ""))
            report.text_outputs_checked += 1
            if _mentions_a_real_identifier(text, identifiers):
                report.text_outputs_grounded += 1
            else:
                report.ungrounded_examples.append(text)

        elif result.task_type == "investigation_hypothesis":
            for hypothesis in result.parsed_output.get("hypotheses", []):
                report.text_outputs_checked += 1
                if _mentions_a_real_identifier(str(hypothesis), identifiers):
                    report.text_outputs_grounded += 1
                else:
                    report.ungrounded_examples.append(str(hypothesis))

        elif result.task_type == "mitre_suggestion":
            techniques = result.parsed_output.get("techniques", [])
            report.mitre_suggestions_checked += 1
            suggested_ids = {t.get("technique_id") for t in techniques}
            if suggested_ids & rule_technique_ids:
                report.mitre_suggestions_overlapping += 1

    return report
