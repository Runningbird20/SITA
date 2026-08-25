"""Orchestrates the six Phase 7 triage tasks against every (or one)
Incident, calling LLMProvider.generate() and persisting AnalysisResult
rows. See DEF.md § Phase 7.

Idempotent/re-runnable: a task is skipped (no LLM call, no new row) if an
AnalysisResult already exists for that incident/task_type/prompt_version,
unless `force=True`. Bumping a prompt's version is the intended way to
force regeneration of just that task.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.registry import default_llm_config, get_llm_provider
from app.llm.types import LLMConfig, LLMRequest
from app.models.analysis_result import AnalysisResult
from app.models.associations import AlertMitreMapping
from app.models.enums import (
    AnalysisTaskType,
    AnalysisValidationStatus,
    MitreMappingSource,
    RecommendationPriority,
    RecommendationSource,
    RecommendationStatus,
)
from app.models.incident import Incident
from app.models.mitre import MITRETechnique
from app.models.recommendation import Recommendation
from app.schemas.triage_run import TriageRunReport
from app.triage import prompts
from app.triage.context import build_incident_context, render_context_block
from app.triage.schemas import (
    AttackClassificationOutput,
    IncidentSummaryOutput,
    InvestigationHypothesisOutput,
    InvestigationStepsOutput,
    MitreSuggestionOutput,
    SeverityExplanationOutput,
)


@dataclass(frozen=True)
class _TriageTask:
    task_type: AnalysisTaskType
    prompt_version: str
    build_prompt: Callable[[str], str]
    response_schema: type[BaseModel]


TASKS: list[_TriageTask] = [
    _TriageTask(
        AnalysisTaskType.INCIDENT_SUMMARY,
        prompts.PROMPT_VERSION_INCIDENT_SUMMARY,
        prompts.build_incident_summary_prompt,
        IncidentSummaryOutput,
    ),
    _TriageTask(
        AnalysisTaskType.SEVERITY_EXPLANATION,
        prompts.PROMPT_VERSION_SEVERITY_EXPLANATION,
        prompts.build_severity_explanation_prompt,
        SeverityExplanationOutput,
    ),
    _TriageTask(
        AnalysisTaskType.ATTACK_CLASSIFICATION,
        prompts.PROMPT_VERSION_ATTACK_CLASSIFICATION,
        prompts.build_attack_classification_prompt,
        AttackClassificationOutput,
    ),
    _TriageTask(
        AnalysisTaskType.INVESTIGATION_HYPOTHESIS,
        prompts.PROMPT_VERSION_INVESTIGATION_HYPOTHESIS,
        prompts.build_investigation_hypothesis_prompt,
        InvestigationHypothesisOutput,
    ),
    _TriageTask(
        AnalysisTaskType.INVESTIGATION_STEPS,
        prompts.PROMPT_VERSION_INVESTIGATION_STEPS,
        prompts.build_investigation_steps_prompt,
        InvestigationStepsOutput,
    ),
    _TriageTask(
        AnalysisTaskType.MITRE_SUGGESTION,
        prompts.PROMPT_VERSION_MITRE_SUGGESTION,
        prompts.build_mitre_suggestion_prompt,
        MitreSuggestionOutput,
    ),
]


def _load_incidents(
    db: Session, incident_id: uuid.UUID | None, since: datetime | None
) -> list[Incident]:
    if incident_id is not None:
        incident = db.get(Incident, incident_id)
        return [incident] if incident is not None else []
    stmt = select(Incident)
    if since is not None:
        stmt = stmt.where(Incident.last_activity_at >= since)
    stmt = stmt.order_by(Incident.last_activity_at)
    return list(db.scalars(stmt).all())


def _existing_result(db: Session, incident: Incident, task: _TriageTask) -> AnalysisResult | None:
    stmt = select(AnalysisResult).where(
        AnalysisResult.incident_id == incident.id,
        AnalysisResult.task_type == task.task_type,
        AnalysisResult.prompt_version == task.prompt_version,
    )
    return db.scalars(stmt).first()


def _apply_investigation_steps(db: Session, incident: Incident, result: AnalysisResult) -> int:
    created = 0
    for step in result.parsed_output["steps"]:
        db.add(
            Recommendation(
                incident_id=incident.id,
                source=RecommendationSource.LLM,
                analysis_result_id=result.id,
                text=step["text"],
                priority=RecommendationPriority(step["priority"]),
                status=RecommendationStatus.OPEN,
            )
        )
        created += 1
    return created


def _apply_mitre_suggestions(db: Session, incident: Incident, result: AnalysisResult) -> int:
    created = 0
    for suggestion in result.parsed_output["techniques"]:
        technique = db.scalars(
            select(MITRETechnique).where(MITRETechnique.technique_id == suggestion["technique_id"])
        ).first()
        if technique is None:
            # Not (yet) in the local vendored dataset — Phase 8's job. The
            # raw suggestion is still preserved in result.parsed_output.
            continue
        for alert in incident.alerts:
            already_mapped = any(
                mapping.technique_id == technique.id and mapping.source == MitreMappingSource.LLM
                for mapping in alert.mitre_mappings
            )
            if already_mapped:
                continue
            db.add(
                AlertMitreMapping(
                    alert_id=alert.id,
                    technique_id=technique.id,
                    source=MitreMappingSource.LLM,
                    analysis_result_id=result.id,
                )
            )
            created += 1
    return created


def run_triage(
    db: Session,
    incident_id: uuid.UUID | None = None,
    since: datetime | None = None,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
    force: bool = False,
) -> TriageRunReport:
    provider = provider if provider is not None else get_llm_provider()
    config = config if config is not None else default_llm_config()

    incidents = _load_incidents(db, incident_id, since)

    analysis_results_created = 0
    analysis_results_skipped = 0
    recommendations_created = 0
    mitre_mappings_created = 0
    by_task_type: dict[str, int] = {task.task_type.value: 0 for task in TASKS}

    for incident in incidents:
        context_block = render_context_block(build_incident_context(incident))

        for task in TASKS:
            if not force and _existing_result(db, incident, task) is not None:
                analysis_results_skipped += 1
                continue

            request = LLMRequest(
                task_type=task.task_type,
                prompt=task.build_prompt(context_block),
                response_schema=task.response_schema,
                prompt_version=task.prompt_version,
            )
            response = provider.generate(request, config)

            result = AnalysisResult(
                incident_id=incident.id,
                alert_id=None,
                task_type=task.task_type,
                provider=response.provider,
                model=response.model,
                prompt_version=response.prompt_version,
                raw_output=response.raw_output,
                parsed_output=response.parsed_output,
                validation_status=response.validation_status,
                confidence=response.confidence,
                latency_ms=response.latency_ms,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
            )
            db.add(result)
            db.flush()
            analysis_results_created += 1
            by_task_type[task.task_type.value] += 1

            if response.validation_status == AnalysisValidationStatus.VALID:
                if task.task_type == AnalysisTaskType.INVESTIGATION_STEPS:
                    recommendations_created += _apply_investigation_steps(db, incident, result)
                elif task.task_type == AnalysisTaskType.MITRE_SUGGESTION:
                    mitre_mappings_created += _apply_mitre_suggestions(db, incident, result)

    db.flush()

    return TriageRunReport(
        since=since,
        incidents_processed=len(incidents),
        analysis_results_created=analysis_results_created,
        analysis_results_skipped=analysis_results_skipped,
        recommendations_created=recommendations_created,
        mitre_mappings_created=mitre_mappings_created,
        by_task_type=by_task_type,
    )
