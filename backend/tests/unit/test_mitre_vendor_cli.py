from pathlib import Path

from app.mitre.vendor_cli import _clean_description, build_dataset_from_bundle, main


def _bundle(objects: list[dict]) -> dict:
    return {"type": "bundle", "objects": objects}


def _attack_pattern(**overrides) -> dict:
    base = {
        "type": "attack-pattern",
        "name": "Test Technique",
        "description": "A technique for testing.",
        "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "execution"}],
        "external_references": [
            {"source_name": "mitre-attack", "external_id": "T9001", "url": "https://example.com"}
        ],
    }
    base.update(overrides)
    return base


class TestCleanDescription:
    def test_strips_citation_markers(self):
        assert _clean_description("Foo bar (Citation: Some Report 2020) baz.") == "Foo bar baz."

    def test_strips_code_tags(self):
        assert _clean_description("Run <code>whoami</code> to check.") == "Run whoami to check."

    def test_keeps_markdown_link_label_drops_url(self):
        assert (
            _clean_description("See [this report](https://example.com/x) for details.")
            == "See this report for details."
        )

    def test_collapses_whitespace(self):
        assert _clean_description("Line one.\n\nLine   two.") == "Line one. Line two."


class TestBuildDatasetFromBundle:
    def test_extracts_a_valid_technique(self):
        bundle = _bundle(
            [
                {
                    "type": "x-mitre-collection",
                    "name": "Enterprise ATT&CK",
                    "x_mitre_version": "19.2",
                },
                _attack_pattern(),
            ]
        )
        dataset = build_dataset_from_bundle(bundle)
        assert dataset.dataset_version == "attack-enterprise-v19.2"
        assert len(dataset.techniques) == 1
        assert dataset.techniques[0].technique_id == "T9001"
        assert dataset.techniques[0].tactic == "execution"

    def test_skips_revoked_and_deprecated(self):
        bundle = _bundle(
            [
                _attack_pattern(revoked=True),
                _attack_pattern(x_mitre_deprecated=True),
                _attack_pattern(),
            ]
        )
        dataset = build_dataset_from_bundle(bundle)
        assert len(dataset.techniques) == 1

    def test_skips_non_attack_pattern_objects(self):
        bundle = _bundle([{"type": "malware", "name": "Not a technique"}])
        assert build_dataset_from_bundle(bundle).techniques == []

    def test_skips_entries_with_no_kill_chain_phases(self):
        bundle = _bundle([_attack_pattern(kill_chain_phases=[])])
        assert build_dataset_from_bundle(bundle).techniques == []

    def test_skips_entries_not_sourced_from_mitre_attack(self):
        bundle = _bundle(
            [
                _attack_pattern(
                    external_references=[{"source_name": "some-other-source", "external_id": "X1"}]
                )
            ]
        )
        assert build_dataset_from_bundle(bundle).techniques == []

    def test_first_kill_chain_phase_wins_for_multi_tactic_techniques(self):
        bundle = _bundle(
            [
                _attack_pattern(
                    kill_chain_phases=[
                        {"kill_chain_name": "mitre-attack", "phase_name": "defense-evasion"},
                        {"kill_chain_name": "mitre-attack", "phase_name": "privilege-escalation"},
                    ]
                )
            ]
        )
        assert build_dataset_from_bundle(bundle).techniques[0].tactic == "defense-evasion"

    def test_results_are_sorted_by_technique_id(self):
        bundle = _bundle(
            [
                _attack_pattern(
                    external_references=[{"source_name": "mitre-attack", "external_id": "T9002"}]
                ),
                _attack_pattern(
                    external_references=[{"source_name": "mitre-attack", "external_id": "T9001"}]
                ),
            ]
        )
        ids = [t.technique_id for t in build_dataset_from_bundle(bundle).techniques]
        assert ids == ["T9001", "T9002"]

    def test_falls_back_to_unknown_version_without_a_collection_object(self):
        dataset = build_dataset_from_bundle(_bundle([_attack_pattern()]))
        assert dataset.dataset_version == "attack-enterprise-vunknown"


class TestMain:
    def test_writes_the_dataset_to_the_output_path(self, monkeypatch, tmp_path, capsys):
        bundle = _bundle(
            [
                {
                    "type": "x-mitre-collection",
                    "name": "Enterprise ATT&CK",
                    "x_mitre_version": "1.0",
                },
                _attack_pattern(),
            ]
        )
        monkeypatch.setattr("app.mitre.vendor_cli.fetch_bundle", lambda url: bundle)
        output_path = tmp_path / "techniques.json"

        exit_code = main(["--output", str(output_path)])

        assert exit_code == 0
        assert output_path.exists()
        assert "T9001" in output_path.read_text()
        assert "Wrote 1 techniques" in capsys.readouterr().out

    def test_output_path_accepts_a_path_object(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "app.mitre.vendor_cli.fetch_bundle", lambda url: _bundle([_attack_pattern()])
        )
        output_path: Path = tmp_path / "out.json"
        assert main(["--output", str(output_path)]) == 0
