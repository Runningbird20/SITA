"""One-time (or periodically re-run) vendoring step: fetch the real MITRE
ATT&CK Enterprise matrix from its official public STIX bundle and write it
into data/mitre/techniques.json, in the exact shape app/mitre/loader.py
already expects. See DEF.md § Phase 8 "Post-roadmap addition: full ATT&CK
Enterprise vendoring".

This is a build-time/setup-time script, not something the running
application ever calls — matching this project's "no runtime cloud
dependency" principle. `data/mitre/techniques.json` itself is checked in
and loaded with zero network access by app.mitre.loader; only re-running
this script to pick up a newer ATT&CK release needs connectivity.

Usage:
    uv run python -m app.mitre.vendor_cli [--output PATH] [--url URL]
"""

import argparse
import json
import re
import sys
from pathlib import Path

import httpx

from app.mitre.loader import DEFAULT_DATASET_PATH, MitreDataset, MitreTechniqueRecord

ATTACK_STIX_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
    "master/enterprise-attack/enterprise-attack.json"
)

_CITATION_RE = re.compile(r"\s*\(Citation:[^)]*\)")
_CODE_TAG_RE = re.compile(r"</?code>")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def _clean_description(raw: str) -> str:
    """STIX descriptions carry markdown links, `<code>` tags, and inline
    `(Citation: ...)` markers meant for the attack.mitre.org website's
    rendering, not for an LLM prompt or a data dictionary — stripped here
    rather than at every read site.
    """
    text = _MD_LINK_RE.sub(r"\1", raw)
    text = _CITATION_RE.sub("", text)
    text = _CODE_TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_technique(obj: dict) -> MitreTechniqueRecord | None:
    """None for anything that isn't a currently-active, ATT&CK-sourced
    technique with a real tactic — revoked/deprecated entries, and the
    handful of objects missing kill_chain_phases entirely, are skipped
    rather than vendored with a guessed value.
    """
    if obj.get("revoked") or obj.get("x_mitre_deprecated"):
        return None
    external_refs = obj.get("external_references") or []
    if not external_refs or external_refs[0].get("source_name") != "mitre-attack":
        return None
    technique_id = external_refs[0].get("external_id")
    kill_chain_phases = obj.get("kill_chain_phases") or []
    if not technique_id or not kill_chain_phases:
        return None

    # A technique can span multiple tactics (kill_chain_phases) — the
    # local schema stores one `tactic: str` per technique (matching the
    # original curated dataset's shape, and nothing downstream needs more
    # than a primary tactic today), so only the first-listed one is kept.
    # A deliberate simplification, not an oversight — see DEF.md § Phase 8.
    tactic = kill_chain_phases[0]["phase_name"]

    return MitreTechniqueRecord(
        technique_id=technique_id,
        name=obj["name"],
        tactic=tactic,
        description=_clean_description(obj.get("description", "")),
    )


def build_dataset_from_bundle(bundle: dict) -> MitreDataset:
    """Pure transform, unit-testable without any network access — the
    actual HTTP fetch lives only in fetch_bundle() below.
    """
    version = "unknown"
    for obj in bundle.get("objects", []):
        if obj.get("type") == "x-mitre-collection":
            version = obj.get("x_mitre_version", version)
            break

    records: list[MitreTechniqueRecord] = []
    seen_ids: set[str] = set()
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        record = _extract_technique(obj)
        if record is None or record.technique_id in seen_ids:
            continue
        seen_ids.add(record.technique_id)
        records.append(record)

    records.sort(key=lambda r: r.technique_id)
    return MitreDataset(dataset_version=f"attack-enterprise-v{version}", techniques=records)


def fetch_bundle(url: str = ATTACK_STIX_URL) -> dict:
    response = httpx.get(url, timeout=60.0, follow_redirects=True)
    response.raise_for_status()
    return response.json()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", type=str, default=ATTACK_STIX_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_DATASET_PATH)
    args = parser.parse_args(argv)

    bundle = fetch_bundle(args.url)
    dataset = build_dataset_from_bundle(bundle)
    args.output.write_text(json.dumps(dataset.model_dump(), indent=2) + "\n")

    print(
        f"Wrote {len(dataset.techniques)} techniques ({dataset.dataset_version}) to {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
