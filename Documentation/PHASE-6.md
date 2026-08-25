# Phase 6: Local LLM Integration — Completion Report

Status: complete. This document explains what was built, how the pieces fit together, and why each decision was made. For the field-level interface and type definitions, see [DEF.md § Phase 6](DEF.md#phase-6-local-llm-integration) — that document is the data dictionary; this one is the narrative of how it got implemented and what tradeoffs that involved. For the checklist itself, see [TODO.md](../TODO.md#phase-6-local-llm-integration).

## Goal

Per TODO.md's own framing: "A clean provider abstraction so the AI layer is swappable, testable without Ollama running, and never a single point of failure for the system." Phase 6 deliberately does not write any real triage prompts — that's Phase 7. Its job is narrower and more foundational: prove that talking to a model, enforcing structured output, handling timeouts/retries, and deriving a trustworthy confidence value all work correctly, using an illustrative example schema, before any real AI-generated content exists anywhere in the system.

## What was built

### One interface, two providers, no duplicated retry logic

`LLMProvider` (`backend/app/llm/base.py`) is an ABC where `generate(request, config) -> LLMResponse` is concrete on the base class — retry/timeout handling, structured-output validation, confidence derivation, and structured logging are identical regardless of which model answers, so they live once, not once per provider. Subclasses implement only `_complete(prompt, config) -> RawCompletion`: one unretried call to the underlying model, raising `LLMTimeoutError` or `LLMProviderError` on failure and letting `generate()` decide whether to retry.

`MockProvider` (`backend/app/llm/mock_provider.py`) and `OllamaProvider` (`backend/app/llm/ollama_provider.py`) both go through the *exact same* `generate()` path — nothing about retry counting, validation, or confidence math is mock-specific. `MockProvider` takes either `responses` (a single canned `RawCompletion`, or a list consumed as a queue — useful for scripting a "fails twice, then succeeds" sequence) or `raises` (an exception to raise every call), never both. `OllamaProvider` makes a synchronous `httpx.post` (not `AsyncClient` — matching this project's fully synchronous architecture everywhere else) to `/api/generate` with `"format": "json"` to enforce structured output at the model layer, translating `httpx.TimeoutException` → `LLMTimeoutError` and any other `httpx.HTTPError` → `LLMProviderError`.

### `generate()` never raises

Every failure mode — timeout, connection error, invalid/malformed output — becomes a returned `LLMResponse` with `validation_status` set to `timeout`, `provider_error`, or `invalid`, never an exception a caller has to remember to catch. This is what lets the system "continue operating on deterministic results alone" when AI analysis is unavailable, per TODO.md's own failure-handling requirement: a caller can always inspect `validation_status` and proceed, rather than needing a try/except around every call site.

### Structured output validation is one function, reused by every failure path

`validate_structured_output()` (`backend/app/llm/validation.py`) calls Pydantic's `model_validate_json()` on the raw response text against the caller-supplied schema. A single exception type, `pydantic.ValidationError`, covers both malformed JSON and schema mismatches, so there's exactly one failure branch to handle, not two:

```python
def validate_structured_output(
    raw_text: str, schema: type[BaseModel]
) -> tuple[dict | None, AnalysisValidationStatus, str | None]:
    try:
        instance = schema.model_validate_json(raw_text)
    except ValidationError as exc:
        return None, AnalysisValidationStatus.INVALID, str(exc)
    return instance.model_dump(mode="json"), AnalysisValidationStatus.VALID, None
```

### Confidence is derived, never self-reported

TODO.md's own "How AI confidence should be represented" open question already leaned toward a derived value rather than trusting a model's self-reported certainty — local models are notoriously unreliable at rating themselves. Phase 6 resolves this concretely using only data `generate()` already has: confidence starts at `1.0` for a response validated on the first attempt, drops by `0.15` per retry actually consumed, floors at `0.5`, and is `None` for any response that never validates. This reflects how much the *validation process* had to fight to get a usable answer, not anything the model claims about itself.

### Retry semantics: bounded, uniform across all three failure kinds

`total_attempts = config.max_retries + 1`. A timeout, a provider error, and an invalid-JSON response are all retried identically — same backoff (`config.retry_backoff_seconds`), same attempt counting, same eventual fallback to a failure `LLMResponse` once attempts are exhausted. `max_retries=0` means exactly one attempt, no special-casing required.

### Everything model-related is config-driven, not hardcoded

`get_llm_provider()` and `default_llm_config()` (`backend/app/llm/registry.py`) are the entire "swapping providers requires no code changes elsewhere" mechanism — callers use these two functions and never import `MockProvider` or `OllamaProvider` directly. `default_llm_config()` reads every field (`model`, `temperature`, `max_tokens`, `timeout_seconds`, `max_retries`, `retry_backoff_seconds`) from `Settings`, which itself sources them from `.env` via `llm_provider`, `ollama_model`, `llm_temperature`, `llm_max_tokens`, `llm_request_timeout_seconds`, `llm_max_retries`, `llm_retry_backoff_seconds`. `Settings.llm_provider` defaults to `"mock"` — the real, unmodified project default, meaning the app runs with zero LLM network dependency out of the box, and switching to Ollama is a single `.env` line, `LLM_PROVIDER=ollama`.

### A diagnostic CLI, not a pipeline CLI

Unlike Phase 3–5's batch-job CLIs, `backend/app/llm/cli.py` has no dataset to run against — there's no batch of anything yet. It's a manual smoke-test: `uv run python -m app.llm.cli "some prompt"` builds a minimal request against whichever provider `get_llm_provider()` returns and prints the resulting `LLMResponse`, so a real Ollama round-trip can be checked by hand without writing a throwaway script every time.

## How it all connects

```
DEF.md § Phase 6 (interface, types, retry semantics, confidence formula — written first)
   │
   ├──→ app/llm/exceptions.py     (LLMTimeoutError, LLMProviderError)
   ├──→ app/llm/types.py          (LLMConfig, LLMRequest, RawCompletion, LLMResponse)
   ├──→ app/llm/validation.py     (validate_structured_output)
   │
   ├──→ app/llm/base.py :: LLMProvider
   │        │  generate() — concrete: retry loop, validation, confidence, logging
   │        │  _complete() — abstract: one unretried model call
   │        │
   │        ├──→ app/llm/mock_provider.py    (MockProvider — zero network I/O)
   │        └──→ app/llm/ollama_provider.py  (OllamaProvider — sync httpx → /api/generate)
   │
   ├──→ app/llm/registry.py
   │        get_llm_provider()      (Settings.llm_provider → Mock or Ollama)
   │        default_llm_config()    (every LLMConfig field sourced from Settings)
   │
   └──→ app/llm/cli.py
        (uv run python -m app.llm.cli "prompt" — manual round-trip smoke-test)
```

`LLMResponse`'s fields map 1:1 onto `AnalysisResult`'s columns (minus the row-linkage fields only a caller knows) — `AnalysisResult` was designed in Phase 1 specifically to record this call's outcome. Phase 6 produces the value; Phase 7 is what actually calls `generate()` from a real pipeline step and persists the row.

## Key decisions and why

| Decision | Reasoning |
|---|---|
| `generate()` concrete on the base class, only `_complete()` abstract | Retry/timeout/validation/confidence/logging are identical for every provider — the same template-method shape already used for `DetectionRule` in Phase 3 |
| `generate()` never raises | Lets every caller check `validation_status` instead of wrapping every call site in try/except; is what actually makes "the system continues on deterministic results alone" true in code, not just in the DoD sentence |
| Confidence derived from retry count, never self-reported by the model | Resolves TODO.md's open question directly; local models are unreliable self-raters, but "how hard did validation have to work" is data `generate()` already has for free |
| `MockProvider` goes through the identical `generate()` path as `OllamaProvider` | Proves the retry/validation/confidence machinery is provider-agnostic rather than accidentally coupled to one implementation; also means tests exercise the real logic, not a parallel test-only code path |
| Synchronous `httpx.post`, not `AsyncClient` | Matches this project's fully synchronous architecture everywhere else — no other module uses asyncio, and introducing it here alone would be a second concurrency model for no benefit |
| `prompt_version` is a plain string tag, not a templating engine | There are no real prompts yet to template — Phase 7's job. Building templating infrastructure now, with nothing real to template, would be exactly the kind of ahead-of-need work this project avoids |
| No REST endpoint | Same Phase 9 deferral as Phase 3/4/5 — and the same honest dashboard consequence: static yellow "Implemented," not live-checked "Working" |
| No database interaction at all this phase | `LLMProvider`/`MockProvider`/`OllamaProvider` are pure in-memory/network components; writing `LLMResponse` into `AnalysisResult` rows is Phase 7's job, so there was nothing to verify against Postgres this phase |

## Verification performed

- 33 new unit tests: `test_llm_validation.py` (valid/invalid JSON, schema mismatches), `test_llm_mock_provider.py` (construction guardrails, repeating vs. queued responses, forced-failure modes), `test_llm_generate.py` (first-attempt success, invalid-then-valid recovery with exact confidence math verified — `0.85` after one retry — confidence floor at `0.5` after 4 retries, exhausted-retries behavior for each of invalid/timeout/provider-error, `max_retries=0` meaning exactly one attempt, provider/model/prompt_version/token pass-through, "never raises" under every failure mode), `test_llm_ollama_provider.py` (monkeypatched `httpx.post`, exception translation), `test_llm_registry.py` (provider selection by config, real default confirmed to be `mock`), `test_llm_cli.py` (success/failure exit codes, output formatting).
- `backend/tests/integration/test_llm_ollama_live.py` — an opportunistic test against a real, locally running Ollama instance. Verification went beyond `MockProvider`-only testing: a real Ollama container was started and a small model (`qwen2.5:0.5b`) pulled specifically for hand-verification, without changing the project's real recommended default (`llama3.1:8b-instruct-q4_K_M`). Both the integration test and the diagnostic CLI were confirmed to genuinely round-trip against the live container (the CLI returned `response: Paris` for "capital of France").
- **A real bug found by this verification, not by inspection**: the live test's skip-check, `_ollama_reachable()`, originally verified only that the Ollama *server* responded to a GET request — not that the specific `settings.ollama_model` was actually pulled. Running the full suite without a manual model override produced a confusing `HTTP 404` test failure instead of a clean skip, because the container only had the small verification model, not the real configured default. Fixed by replacing the check with one that queries `GET /api/tags` and confirms the configured model is present in the response before running — matching the test's own stated design intent of never failing on a machine where Ollama is only partially set up. This is the same "caught by actually running it, not by reading the code" pattern that found real bugs in Phase 4 (`.example` domains) and Phase 5 (RFC 5737 ranges).
- `ruff check` / `ruff format --check` pass clean. Full backend suite: 225 passed, 1 skipped (the live Ollama test, correctly skipping in this environment since only the small verification model is pulled), 0 failed.
- Frontend dashboard updated to show Phase 6 as a static yellow "Implemented" (same convention as Phase 3/4/5 — no REST endpoint to live-check); `npm run lint` and `npm run build` both confirmed clean after the change.

## What Phase 6 deliberately does not include

**No real triage prompts or task schemas** — the CLI's `_DiagnosticResponse` and the unit tests' `_ExampleSchema` are illustrative only; Phase 7 writes the actual incident-summarization, severity-explanation, and classification prompts and schemas. **No prompt template management system** — `prompt_version` is a plain string the caller assigns; there's nothing real to template yet. **No REST endpoint** — same Phase 9 deferral as every prior deterministic-pipeline phase. **No persistence** — `LLMResponse` is a plain dataclass returned to the caller; writing it into an `AnalysisResult` row is Phase 7's job, which is also why this phase required no Postgres verification. **No pipeline integration** — nothing in `ingestion → detection → IOC extraction → correlation` calls `generate()` yet; Phase 6 proves the provider layer works in isolation, Phase 7 is what wires it into the system's actual triage flow.
