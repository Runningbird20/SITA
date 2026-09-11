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
    # Individual suggested technique_id values, across every mitre_suggestion
    # result — finer-grained than the per-result counters above, since one
    # result can suggest several IDs, some real and some not. Added
    # post-roadmap alongside full ATT&CK Enterprise vendoring (see DEF.md §
    # Phase 8 "Post-roadmap addition: full ATT&CK Enterprise vendoring") —
    # with only 8 curated techniques, "does this ID exist locally" was a
    # weak signal (most real IDs wouldn't exist regardless); with ~700
    # vendored, it's a real check for "did the model invent a technique_id"
    # distinct from "did it happen to overlap with the rule mapping."
    mitre_technique_ids_suggested: int = 0
    mitre_technique_ids_valid: int = 0
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

    @property
    def mitre_suggestion_validity_rate(self) -> float | None:
        return (
            self.mitre_technique_ids_valid / self.mitre_technique_ids_suggested
            if self.mitre_technique_ids_suggested
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
            "mitre_technique_ids_suggested": self.mitre_technique_ids_suggested,
            "mitre_technique_ids_valid": self.mitre_technique_ids_valid,
            "mitre_suggestion_validity_rate": self.mitre_suggestion_validity_rate,
            "ungrounded_examples": self.ungrounded_examples,
        }


def real_identifiers(incident: Incident) -> set[str]:
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


def mentions_a_real_identifier(text: str, identifiers: set[str]) -> bool:
    lowered = text.lower()
    return any(identifier in lowered for identifier in identifiers)


def evaluate_grounding(
    incident: Incident,
    results: list[AnalysisResult],
    mitre_rollup: list[IncidentTechniqueEntry],
    known_technique_ids: set[str] | None = None,
) -> GroundingReport:
    """`known_technique_ids`: every technique_id in the local vendored
    dataset (e.g. `set(db.scalars(select(MITRETechnique.technique_id)))`),
    used to score `mitre_suggestion_validity_rate`. Optional — omitted
    (None), the validity counters simply stay at zero/None, same as any
    other check this function skips when its inputs aren't available.
    """
    report = GroundingReport()
    identifiers = real_identifiers(incident)
    rule_technique_ids = {entry.technique_id for entry in mitre_rollup if "rule" in entry.sources}

    for result in results:
        if result.validation_status != "valid" or not result.parsed_output:
            continue

        if result.task_type == "incident_summary":
            text = str(result.parsed_output.get("summary", ""))
            report.text_outputs_checked += 1
            if mentions_a_real_identifier(text, identifiers):
                report.text_outputs_grounded += 1
            else:
                report.ungrounded_examples.append(text)

        elif result.task_type == "investigation_hypothesis":
            for hypothesis in result.parsed_output.get("hypotheses", []):
                report.text_outputs_checked += 1
                if mentions_a_real_identifier(str(hypothesis), identifiers):
                    report.text_outputs_grounded += 1
                else:
                    report.ungrounded_examples.append(str(hypothesis))

        elif result.task_type == "attack_classification":
            # Added post-roadmap alongside the triage pipeline's
            # grounding-aware retry (see DEF.md § 8 AnalysisResult,
            # "Grounding-aware retry") — this is exactly the field that
            # produced the confirmed hallucinated "ransomware" finding, so
            # measurement now covers what the retry logic acts on.
            text = str(result.parsed_output.get("rationale", ""))
            report.text_outputs_checked += 1
            if mentions_a_real_identifier(text, identifiers):
                report.text_outputs_grounded += 1
            else:
                report.ungrounded_examples.append(text)

        elif result.task_type == "mitre_suggestion":
            techniques = result.parsed_output.get("techniques", [])
            report.mitre_suggestions_checked += 1
            suggested_ids = {t.get("technique_id") for t in techniques}
            if suggested_ids & rule_technique_ids:
                report.mitre_suggestions_overlapping += 1
            if known_technique_ids is not None:
                report.mitre_technique_ids_suggested += len(suggested_ids)
                report.mitre_technique_ids_valid += len(suggested_ids & known_technique_ids)

    return report
