"""Manual smoke-test for the configured LLM provider — not a pipeline CLI
like Phase 3-5's (there's no batch job here), just a way to check a real
round-trip by hand without writing a throwaway script.

Usage:
    uv run python -m app.llm.cli "some prompt"
"""

import sys

from pydantic import BaseModel

from app.llm.registry import default_llm_config, get_llm_provider
from app.llm.types import LLMRequest
from app.models.enums import AnalysisTaskType


class _DiagnosticResponse(BaseModel):
    """A trivial schema used only by this CLI, to prove a real structured
    JSON round-trip — not one of Phase 7's actual task schemas.
    """

    response: str


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print('Usage: uv run python -m app.llm.cli "some prompt"', file=sys.stderr)
        return 1

    user_prompt = " ".join(argv)
    prompt = (
        f"{user_prompt}\n\n"
        'Respond with a single JSON object of the exact shape {"response": "<your answer as a string>"} '
        "and nothing else."
    )

    provider = get_llm_provider()
    config = default_llm_config()
    request = LLMRequest(
        task_type=AnalysisTaskType.INCIDENT_SUMMARY,
        prompt=prompt,
        response_schema=_DiagnosticResponse,
        prompt_version="cli-diagnostic-v1",
    )

    response = provider.generate(request, config)

    print(f"provider:          {response.provider}")
    print(f"model:             {response.model}")
    print(f"validation_status: {response.validation_status.value}")
    print(f"latency_ms:        {response.latency_ms}")
    print(f"confidence:        {response.confidence}")
    if response.parsed_output is not None:
        print(f"response:          {response.parsed_output.get('response')}")
    else:
        print(f"raw_output:        {response.raw_output!r}")
        print(f"error:             {response.error}")

    return 0 if response.validation_status.value == "valid" else 1


if __name__ == "__main__":
    sys.exit(main())
