import json

from sqlalchemy import select

from app.chat.service import ask_incident_question
from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.ioc.pipeline import run_ioc_extraction
from app.llm.exceptions import LLMTimeoutError
from app.llm.mock_provider import MockProvider
from app.llm.types import LLMConfig, RawCompletion
from app.models.chat_message import ChatMessage
from app.models.enums import AnalysisValidationStatus, ChatRole
from app.models.incident import Incident

_FAST_CONFIG = LLMConfig(model="test-model", max_retries=0, retry_backoff_seconds=0)


def _make_incident(db_session, brute_force_events) -> Incident:
    brute_force_events()
    db_session.commit()
    run_detection(db_session)
    db_session.commit()
    run_ioc_extraction(db_session)
    db_session.commit()
    run_correlation(db_session)
    db_session.commit()
    return db_session.scalars(select(Incident)).one()


class TestAskIncidentQuestion:
    def test_persists_user_question_and_assistant_answer(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
        provider = MockProvider(
            responses=RawCompletion(text=json.dumps({"answer": "This is a brute-force attempt."}))
        )

        reply = ask_incident_question(
            db_session, incident, "What is this?", provider=provider, config=_FAST_CONFIG
        )
        db_session.commit()

        messages = db_session.scalars(
            select(ChatMessage)
            .where(ChatMessage.incident_id == incident.id)
            .order_by(ChatMessage.created_at)
        ).all()
        assert len(messages) == 2
        assert messages[0].role == ChatRole.USER
        assert messages[0].content == "What is this?"
        assert messages[1].role == ChatRole.ASSISTANT
        assert messages[1].content == "This is a brute-force attempt."
        assert messages[1].validation_status == AnalysisValidationStatus.VALID
        assert reply.id == messages[1].id

    def test_second_question_includes_prior_turn_in_the_prompt(
        self, db_session, brute_force_events
    ):
        incident = _make_incident(db_session, brute_force_events)
        provider = MockProvider(
            responses=[
                RawCompletion(text=json.dumps({"answer": "First answer."})),
                RawCompletion(text=json.dumps({"answer": "Second answer."})),
            ]
        )

        ask_incident_question(
            db_session, incident, "First question?", provider=provider, config=_FAST_CONFIG
        )
        db_session.commit()
        ask_incident_question(
            db_session, incident, "Second question?", provider=provider, config=_FAST_CONFIG
        )
        db_session.commit()

        messages = db_session.scalars(
            select(ChatMessage)
            .where(ChatMessage.incident_id == incident.id)
            .order_by(ChatMessage.created_at)
        ).all()
        assert [m.content for m in messages] == [
            "First question?",
            "First answer.",
            "Second question?",
            "Second answer.",
        ]

    def test_invalid_llm_output_still_persists_the_question_with_a_fallback_answer(
        self, db_session, brute_force_events
    ):
        incident = _make_incident(db_session, brute_force_events)
        provider = MockProvider(responses=RawCompletion(text="not valid json"))

        ask_incident_question(
            db_session, incident, "What happened?", provider=provider, config=_FAST_CONFIG
        )
        db_session.commit()

        messages = db_session.scalars(
            select(ChatMessage)
            .where(ChatMessage.incident_id == incident.id)
            .order_by(ChatMessage.created_at)
        ).all()
        assert len(messages) == 2
        assert messages[0].content == "What happened?"
        assert messages[1].validation_status == AnalysisValidationStatus.INVALID
        assert "wasn't able to generate" in messages[1].content

    def test_provider_timeout_still_persists_the_question(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
        provider = MockProvider(raises=LLMTimeoutError("timed out"))

        ask_incident_question(
            db_session, incident, "Anyone home?", provider=provider, config=_FAST_CONFIG
        )
        db_session.commit()

        messages = db_session.scalars(
            select(ChatMessage)
            .where(ChatMessage.incident_id == incident.id)
            .order_by(ChatMessage.created_at)
        ).all()
        assert len(messages) == 2
        assert messages[0].role == ChatRole.USER
        assert messages[1].validation_status == AnalysisValidationStatus.TIMEOUT
