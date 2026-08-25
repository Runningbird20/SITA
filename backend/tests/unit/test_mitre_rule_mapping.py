import json

from app.detection.registry import RULES
from app.mitre.loader import DEFAULT_DATASET_PATH


class TestEveryRuleMapsToAValidTechnique:
    def test_every_rule_declares_at_least_one_technique(self):
        for rule in RULES:
            assert rule.mitre_technique_ids, f"{rule.rule_key} declares no mitre_technique_ids"

    def test_every_declared_technique_id_exists_in_the_vendored_dataset(self):
        raw = json.loads(DEFAULT_DATASET_PATH.read_text())
        known_ids = {t["technique_id"] for t in raw["techniques"]}

        for rule in RULES:
            for technique_id in rule.mitre_technique_ids:
                assert technique_id in known_ids, (
                    f"{rule.rule_key} declares unknown technique_id {technique_id!r}"
                )
