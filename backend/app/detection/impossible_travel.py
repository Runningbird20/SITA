from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.detection.geoip import GeoIPResolver, StaticGeoIPResolver, haversine_km
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


class ImpossibleTravelRule(DetectionRule):
    rule_key = "impossible_travel"
    name = "Impossible Travel"
    description = (
        "The same user authenticating successfully from two geographically "
        "distant locations within a time window too short for real travel "
        "between them. Relies on a GeoIP resolver — see DEF.md § Phase 3 for "
        "the known limitation that the current resolver is a small static "
        "stub, not a real geolocation database."
    )
    category = DetectionCategory.AUTHENTICATION
    default_severity = Severity.HIGH
    source_types = (SourceType.AUTH,)
    default_config = {"max_plausible_speed_kmh": 900}
    mitre_technique_ids = ("T1078",)

    def __init__(self, geo_resolver: GeoIPResolver | None = None):
        self._geo_resolver = geo_resolver or StaticGeoIPResolver()

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        max_speed = config.get(
            "max_plausible_speed_kmh", self.default_config["max_plausible_speed_kmh"]
        )

        by_username: dict[str, list[SecurityEvent]] = defaultdict(list)
        for event in events:
            if event.normalized.get("event_result") != "success":
                continue
            username = event.normalized.get("username")
            if username:
                by_username[username].append(event)

        findings: list[RuleFinding] = []
        for username, logins in by_username.items():
            logins.sort(key=lambda e: e.occurred_at)
            for prev, curr in zip(logins, logins[1:], strict=False):
                prev_ip = prev.normalized.get("source_ip")
                curr_ip = curr.normalized.get("source_ip")
                if not prev_ip or not curr_ip or prev_ip == curr_ip:
                    continue
                prev_loc = self._geo_resolver.resolve(prev_ip)
                curr_loc = self._geo_resolver.resolve(curr_ip)
                if prev_loc is None or curr_loc is None or prev_loc.label == curr_loc.label:
                    continue

                hours = (curr.occurred_at - prev.occurred_at).total_seconds() / 3600
                if hours <= 0:
                    continue
                distance_km = haversine_km(prev_loc, curr_loc)
                speed_kmh = distance_km / hours
                if speed_kmh <= max_speed:
                    continue

                severity, factors = score_severity(self.default_severity, 1, 1)
                rationale = (
                    f"{username!r} logged in from {prev_loc.label} ({prev_ip}) at "
                    f"{prev.occurred_at.isoformat()}, then from {curr_loc.label} ({curr_ip}) "
                    f"at {curr.occurred_at.isoformat()} — {distance_km:.0f}km in {hours:.2f}h "
                    f"implies {speed_kmh:.0f}km/h, exceeding the plausible-travel threshold "
                    f"of {max_speed}km/h."
                )
                findings.append(
                    RuleFinding(
                        matched_event_ids=[prev.id, curr.id],
                        severity=severity,
                        confidence=0.7,
                        rationale=rationale,
                        severity_factors={**factors, "implied_speed_kmh": round(speed_kmh, 1)},
                        first_event_at=prev.occurred_at,
                        last_event_at=curr.occurred_at,
                    )
                )
        return findings
