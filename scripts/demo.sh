#!/usr/bin/env bash
# One-shot bootstrap: brings up the full stack, applies migrations, loads
# the synthetic security event datasets, and runs the full deterministic
# pipeline (detection -> IOC extraction -> MITRE mapping -> correlation ->
# AI triage) so a reviewer sees a populated, already-triaged dashboard
# immediately. See DEF.md § Phase 15 and TODO.md's Phase 15 "[HIGH VALUE]"
# task.
#
# Requires only Docker. Safe to re-run: skips the data-load step if
# incidents already exist (checked via the real API, not a local marker
# file) rather than re-ingesting and creating duplicates.
#
# Usage: ./scripts/demo.sh

set -euo pipefail

cd "$(dirname "$0")/.."

BACKEND_URL="http://localhost:8000"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example (LLM_PROVIDER=mock by default — zero"
  echo "network dependency; see README to enable real Ollama triage)."
  echo
fi

echo "==> Starting the stack (postgres, ollama, backend, frontend)..."
docker compose up --build -d --wait

echo "==> Applying database migrations..."
docker compose exec -T backend uv run alembic upgrade head

existing_total="$(
  curl -s "$BACKEND_URL/api/v1/incidents?limit=1" \
    | grep -o '"total":[0-9]*' \
    | grep -o '[0-9]*' \
    || echo 0
)"

if [ "${existing_total:-0}" -gt 0 ]; then
  echo "==> $existing_total incident(s) already present — skipping data load"
  echo "    (re-run with a fresh \`docker compose down -v\` to start clean)."
else
  echo "==> Loading synthetic security event data..."
  for source in auth endpoint network dns web; do
    for host_file in data/synthetic_events/"$source"/*.jsonl; do
      [ -f "$host_file" ] || continue
      container_path="/data/synthetic_events/$source/$(basename "$host_file")"
      echo "    - $source: $(basename "$host_file")"
      docker compose exec -T backend \
        uv run python -m app.ingestion.cli "$source" "$container_path"
    done
  done

  for host_file in data/synthetic_events/scenarios/*/*.jsonl; do
    [ -f "$host_file" ] || continue
    scenario_dir="$(basename "$(dirname "$host_file")")"
    source_type="$(basename "$host_file" .jsonl)"
    container_path="/data/synthetic_events/scenarios/$scenario_dir/$(basename "$host_file")"
    echo "    - scenario $scenario_dir ($source_type)"
    docker compose exec -T backend \
      uv run python -m app.ingestion.cli "$source_type" "$container_path"
  done

  echo "==> Loading the vendored MITRE ATT&CK technique dataset..."
  # The pipeline-trigger endpoint's own MITRE-mapping pass only *links*
  # already-loaded techniques (deliberately self-healing, see
  # app/mitre/pipeline.py) — without this step the MITRE page and every
  # incident's technique list stay empty even though mapping ran.
  docker compose exec -T backend uv run python -m app.mitre.cli > /dev/null

  echo "==> Running the full pipeline (detection, IOC extraction, MITRE"
  echo "    mapping, correlation, AI triage)..."
  curl -s -X POST "$BACKEND_URL/api/v1/pipeline/run" \
    -H "Content-Type: application/json" -d '{}' > /dev/null
fi

echo
echo "Dashboard:     http://localhost:5173"
echo "Build status:  http://localhost:5173/status"
echo "API docs:      http://localhost:8000/docs"
