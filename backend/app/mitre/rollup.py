"""The technique display model: groups an Incident's alert-level MITRE
mappings by technique, across both rule and LLM sources. Pure, read-only
functions over already-loaded ORM state — no persistence, no REST endpoint
yet (Phase 9's job). See DEF.md § Phase 8.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from app.models.enums import MitreMappingSource
from app.models.incident import Incident


@dataclass
class TechniqueEvidence:
    alert_id: uuid.UUID
    source: MitreMappingSource
    analysis_result_id: uuid.UUID | None
    confidence: float | None


@dataclass
class IncidentTechniqueEntry:
    technique_id: str
    name: str
    tactic: str
    evidence: list[TechniqueEvidence] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)


def incident_technique_rollup(incident: Incident) -> list[IncidentTechniqueEntry]:
    """Union of MITRE techniques across every alert in the incident. No
    separate "agreement/disagreement" flag is computed — `sources` already
    shows whether a technique came from the rule layer, the LLM, or both,
    since `AlertMitreMapping` keeps them as separate rows per alert.
    """
    entries: dict[str, IncidentTechniqueEntry] = {}

    for alert in incident.alerts:
        for mapping in alert.mitre_mappings:
            technique = mapping.technique
            entry = entries.get(technique.technique_id)
            if entry is None:
                entry = IncidentTechniqueEntry(
                    technique_id=technique.technique_id,
                    name=technique.name,
                    tactic=technique.tactic,
                )
                entries[technique.technique_id] = entry

            source = str(mapping.source)
            entry.sources.add(source)
            entry.evidence.append(
                TechniqueEvidence(
                    alert_id=alert.id,
                    source=mapping.source,
                    analysis_result_id=mapping.analysis_result_id,
                    confidence=(
                        mapping.analysis_result.confidence
                        if source == MitreMappingSource.LLM and mapping.analysis_result is not None
                        else None
                    ),
                )
            )

    return list(entries.values())


def techniques_by_tactic(
    entries: list[IncidentTechniqueEntry],
) -> dict[str, list[IncidentTechniqueEntry]]:
    """`[STRETCH]` grouping for the eventual Phase 10 ATT&CK-matrix view."""
    grouped: dict[str, list[IncidentTechniqueEntry]] = defaultdict(list)
    for entry in entries:
        grouped[entry.tactic].append(entry)
    return dict(grouped)
