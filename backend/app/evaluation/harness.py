"""Runs the deterministic pipeline against the held-out data/eval/ dataset
and computes precision/recall/F1 against ground_truth.json. See DEF.md §
Phase 12. Case-to-event attribution is by exact SecurityEvent id, found via
each case's unique marker host/IP baked in at generation time — never by
parsing rationale text or guessing from time windows.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.evaluation.generate_dataset import EVAL_DIR
from app.ingestion.cli import load_jsonl
from app.ingestion.service import ingest_records
from app.ioc.pipeline import run_ioc_extraction
from app.models.alert import Alert
from app.models.enums import SourceType
from app.models.event import SecurityEvent


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        denom = self.tp + self.fp
        return self.tp / denom if denom else None

    @property
    def recall(self) -> float | None:
        denom = self.tp + self.fn
        return self.tp / denom if denom else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if not p or not r or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    def as_dict(self) -> dict:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
        }


@dataclass
class EvaluationReport:
    detection_by_rule: dict[str, Counts] = field(default_factory=dict)
    detection_overall: Counts = field(default_factory=Counts)
    ioc_by_type: dict[str, Counts] = field(default_factory=dict)
    ioc_overall: Counts = field(default_factory=Counts)
    correlation_correct: int = 0
    correlation_total: int = 0
    correlation_failures: list[str] = field(default_factory=list)

    @property
    def correlation_accuracy(self) -> float | None:
        return self.correlation_correct / self.correlation_total if self.correlation_total else None

    def as_dict(self) -> dict:
        return {
            "detection": {
                "overall": self.detection_overall.as_dict(),
                "by_rule": {
                    rule: c.as_dict() for rule, c in sorted(self.detection_by_rule.items())
                },
            },
            "ioc_extraction": {
                "overall": self.ioc_overall.as_dict(),
                "by_type": {t: c.as_dict() for t, c in sorted(self.ioc_by_type.items())},
            },
            "correlation": {
                "correct": self.correlation_correct,
                "total": self.correlation_total,
                "accuracy": self.correlation_accuracy,
                "failures": self.correlation_failures,
            },
        }


def _ingest_eval_events(db: Session) -> None:
    for path in sorted((EVAL_DIR / "events").glob("*.jsonl")):
        source_type = SourceType(path.stem)
        ingest_records(db=db, source_type=source_type, raw_records=load_jsonl(path), batch_id=None)
    for scenario_dir in sorted((EVAL_DIR / "scenarios").iterdir()):
        if not scenario_dir.is_dir():
            continue
        for path in sorted(scenario_dir.glob("*.jsonl")):
            source_type = SourceType(path.stem)
            ingest_records(
                db=db, source_type=source_type, raw_records=load_jsonl(path), batch_id=None
            )
    db.flush()


def _events_for_marker(db: Session, marker: str) -> set:
    stmt = select(SecurityEvent.id).where(
        (SecurityEvent.source_host == marker)
        | (SecurityEvent.normalized["source_ip"].as_string() == marker)
        | (SecurityEvent.normalized["src_ip"].as_string() == marker)
        | (SecurityEvent.normalized["username"].as_string() == marker)
    )
    return set(db.scalars(stmt).all())


def _evaluate_detection(db: Session, ground_truth: dict, report: EvaluationReport) -> None:
    cases = ground_truth["detection_cases"]
    case_event_ids: dict[str, set] = {
        c["case_id"]: _events_for_marker(db, c["marker"]) for c in cases
    }

    event_id_to_case: dict = {}
    for case_id, event_ids in case_event_ids.items():
        for eid in event_ids:
            event_id_to_case[eid] = case_id

    rules_seen: set[str] = {c["expected_rule_key"] for c in cases if c["expected_rule_key"]}
    fired_rule_by_case: dict[str, set[str]] = defaultdict(set)

    for alert in db.scalars(select(Alert)).all():
        rule_key = alert.detection.rule_key
        rules_seen.add(rule_key)
        owning_cases = {event_id_to_case[e.id] for e in alert.events if e.id in event_id_to_case}
        for case_id in owning_cases:
            fired_rule_by_case[case_id].add(rule_key)

    for rule in rules_seen:
        report.detection_by_rule[rule] = Counts()

    for case in cases:
        case_id = case["case_id"]
        expected_rule = case["expected_rule_key"]
        excused = {*case.get("also_expected_rule_keys", []), expected_rule} - {None}
        fired = fired_rule_by_case.get(case_id, set())

        if expected_rule:
            if expected_rule in fired:
                report.detection_by_rule[expected_rule].tp += 1
                report.detection_overall.tp += 1
            else:
                report.detection_by_rule[expected_rule].fn += 1
                report.detection_overall.fn += 1

        for rule in fired - excused:
            report.detection_by_rule[rule].fp += 1
            report.detection_overall.fp += 1


def _evaluate_iocs(db: Session, ground_truth: dict, report: EvaluationReport) -> None:
    """Per-case, per-event attribution — never a global "any extracted IOC
    I didn't explicitly enumerate counts against precision" comparison,
    which would conflate other correct-but-unlisted extractions (e.g. an
    auth event's source_ip, extracted correctly but not this case's own
    target) with genuine extraction errors. Positive cases check their own
    event's IOCs contain the expected pair; negative cases check the
    forbidden pair is absent.
    """
    types_seen = {
        c["expected_ioc_type"] for c in ground_truth["ioc_cases"] if c["expected_ioc_type"]
    } | {c["forbidden_ioc_type"] for c in ground_truth["ioc_cases"] if c["forbidden_ioc_type"]}
    for t in types_seen:
        report.ioc_by_type[t] = Counts()

    for case in ground_truth["ioc_cases"]:
        event_ids = _events_for_marker(db, case["marker"])
        case_pairs: set[tuple[str, str]] = set()
        for eid in event_ids:
            event = db.get(SecurityEvent, eid)
            case_pairs |= {(str(ioc.ioc_type), ioc.value) for ioc in event.iocs}

        if case["expected_ioc_type"]:
            pair = (case["expected_ioc_type"], case["expected_value"])
            counts = report.ioc_by_type[case["expected_ioc_type"]]
            if pair in case_pairs:
                counts.tp += 1
                report.ioc_overall.tp += 1
            else:
                counts.fn += 1
                report.ioc_overall.fn += 1

        if case["forbidden_ioc_type"]:
            pair = (case["forbidden_ioc_type"], case["forbidden_value"])
            counts = report.ioc_by_type[case["forbidden_ioc_type"]]
            if pair in case_pairs:
                counts.fp += 1
                report.ioc_overall.fp += 1


def _evaluate_correlation(db: Session, ground_truth: dict, report: EvaluationReport) -> None:
    for case in ground_truth["correlation_cases"]:
        markers: list[str] = []
        scenario_dir = EVAL_DIR / "scenarios" / case["case_id"]
        for path in scenario_dir.glob("*.jsonl"):
            for record in load_jsonl(path):
                host = record.get("host")
                if host:
                    markers.append(host)
        event_ids: set = set()
        for marker in set(markers):
            event_ids |= _events_for_marker(db, marker)

        incident_ids = set()
        for alert in db.scalars(select(Alert)).all():
            if any(e.id in event_ids for e in alert.events) and alert.incident_id:
                incident_ids.add(alert.incident_id)

        report.correlation_total += 1
        is_single = len(incident_ids) == 1
        if is_single == case["expect_single_incident"]:
            report.correlation_correct += 1
        else:
            report.correlation_failures.append(
                f"{case['case_id']}: expected single_incident={case['expect_single_incident']}, "
                f"got {len(incident_ids)} incident(s)"
            )


def run_evaluation(db: Session) -> EvaluationReport:
    ground_truth = json.loads((EVAL_DIR / "ground_truth.json").read_text())

    _ingest_eval_events(db)
    db.flush()
    run_detection(db)
    db.flush()
    run_ioc_extraction(db)
    db.flush()
    run_correlation(db)
    db.flush()

    report = EvaluationReport()
    _evaluate_detection(db, ground_truth, report)
    _evaluate_iocs(db, ground_truth, report)
    _evaluate_correlation(db, ground_truth, report)
    return report
