"""Orchestrates one turn of the conversational chat feature: persist the
analyst's question, call LLMProvider.generate() with the incident context
plus prior turns, persist the answer. See DEF.md § Phase 7, "Post-roadmap
addition: a conversational interface with an incident".
"""

from sqlalchemy.orm import Session

from app.llm.base import LLMProvider
from app.llm.registry import default_llm_config, get_llm_provider
from app.llm.types import LLMConfig, LLMRequest
from app.models.chat_message import ChatMessage
from app.models.enums import AnalysisTaskType, AnalysisValidationStatus, ChatRole
from app.models.incident import Incident
from app.triage import prompts
from app.triage.context import build_incident_context, render_context_block
from app.triage.schemas import ChatAnswerOutput

_FAILURE_ANSWER = (
    "I wasn't able to generate an answer for that question — the model's "
    "response didn't come back in a usable form. Try rephrasing the question."
)


def ask_incident_question(
    db: Session,
    incident: Incident,
    question: str,
    provider: LLMProvider | None = None,
    config: LLMConfig | None = None,
) -> ChatMessage:
    """Persists the user's question immediately, then the assistant's
    reply once generated — both rows exist even if generation fails, so
    the thread always shows what was actually asked. Returns the
    assistant ChatMessage (the caller already has the question's text).
    """
    provider = provider if provider is not None else get_llm_provider()
    config = config if config is not None else default_llm_config()

    history = [(msg.role, msg.content) for msg in incident.chat_messages]

    db.add(ChatMessage(incident_id=incident.id, role=ChatRole.USER, content=question))
    db.flush()

    ctx = build_incident_context(incident)
    context_block = render_context_block(ctx)
    prompt = prompts.build_chat_prompt(context_block, history, question)

    request = LLMRequest(
        task_type=AnalysisTaskType.CHAT_RESPONSE,
        prompt=prompt,
        response_schema=ChatAnswerOutput,
        prompt_version=prompts.PROMPT_VERSION_CHAT,
    )
    response = provider.generate(request, config)

    if response.validation_status == AnalysisValidationStatus.VALID:
        content = response.parsed_output["answer"]
    else:
        content = _FAILURE_ANSWER

    assistant_message = ChatMessage(
        incident_id=incident.id,
        role=ChatRole.ASSISTANT,
        content=content,
        provider=response.provider,
        model=response.model,
        prompt_version=response.prompt_version,
        validation_status=response.validation_status,
        confidence=response.confidence,
        latency_ms=response.latency_ms,
    )
    db.add(assistant_message)
    db.flush()
    return assistant_message
