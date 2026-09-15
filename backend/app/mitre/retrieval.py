"""Builds a real, vendored MITRE ATT&CK candidate shortlist for the
mitre_suggestion triage task — the retrieval half of grounding that task's
suggestions in real data instead of the model's own training recall. See
DEF.md § Phase 8 "Post-roadmap addition: candidate-technique retrieval".

Fully deterministic: no embeddings, no external call. Candidates are
selected by (1) sharing a tactic with the incident's already rule-mapped
techniques, then (2) ranked by plain keyword overlap between the
incident's own text (title, alert rationale, detection names, IOC values)
and each candidate technique's name/description. Proportionate to this
project's scale — a from-scratch retrieval layer, not a vector database.
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mitre import MITRETechnique
from app.triage.context import IncidentContext

_TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{2,}")

_STOPWORDS = {
    "the",
    "and",
    "for",
    "from",
    "with",
    "within",
    "this",
    "that",
    "was",
    "were",
    "via",
    "against",
    "one",
    "same",
    "into",
    "onto",
    "than",
    "then",
    "have",
    "has",
    "had",
    "not",
    "are",
    "its",
    "may",
    "can",
    "also",
    "using",
    "used",
    "adversaries",
    "adversary",
}


@dataclass(frozen=True)
class CandidateTechnique:
    technique_id: str
    name: str
    tactic: str
    description: str


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def _incident_keywords(ctx: IncidentContext) -> set[str]:
    parts = [ctx.title]
    for alert in ctx.alerts:
        parts.append(alert.detection_name)
        parts.append(alert.category)
        parts.append(alert.rationale)
    parts.extend(ctx.ioc_summaries)
    return _tokenize(" ".join(parts))


def candidate_techniques_for_incident(
    db: Session, ctx: IncidentContext, limit: int = 12
) -> list[CandidateTechnique]:
    """Excludes technique IDs already in ctx.rule_mitre_techniques — those
    are shown to the model separately, as the deterministic mappings, so
    listing them again here would just be noise.
    """
    already_mapped = set(ctx.rule_mitre_techniques)

    tactics: set[str] = set()
    if already_mapped:
        tactics = set(
            db.scalars(
                select(MITRETechnique.tactic).where(MITRETechnique.technique_id.in_(already_mapped))
            ).all()
        )

    stmt = select(MITRETechnique)
    if tactics:
        stmt = stmt.where(MITRETechnique.tactic.in_(tactics))
    pool = [t for t in db.scalars(stmt).all() if t.technique_id not in already_mapped]

    keywords = _incident_keywords(ctx)

    def _score(technique: MITRETechnique) -> int:
        return len(_tokenize(f"{technique.name} {technique.description}") & keywords)

    pool.sort(key=lambda t: (-_score(t), t.technique_id))

    return [
        CandidateTechnique(
            technique_id=t.technique_id,
            name=t.name,
            tactic=t.tactic,
            description=t.description,
        )
        for t in pool[:limit]
    ]
