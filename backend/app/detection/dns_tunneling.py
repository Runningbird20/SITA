import math
from collections import Counter, defaultdict
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.detection.base import DetectionRule, RuleFinding, score_severity
from app.models.enums import DetectionCategory, Severity, SourceType
from app.models.event import SecurityEvent


def _registry_suffix(query_name: str) -> str:
    """The grouping key for a DNS campaign: the rightmost label alone (the
    TLD or pseudo-TLD — "com", "example", "internal"), not a last-two-labels
    registrable-domain split. Deliberate: DNS tunneling and DGA beaconing
    both cycle through many distinct *left*-hand labels under a shared
    right-hand suffix — sometimes a subdomain under one owned domain,
    sometimes a fully-distinct look-alike SLD per query (this project's own
    fixtures use the latter shape, generating a new random-looking name
    directly under the synthetic ".example" pseudo-TLD per query — see
    data/synthetic_events/dns/suspicious_domain.jsonl). Grouping on the
    bare suffix catches both shapes. This does not false-positive on
    ordinary multi-domain browsing (many distinct real SLDs sharing ".com")
    because the entropy/NXDOMAIN gate below only fires for random-looking
    or failing lookups — English-word SLDs with a near-zero NXDOMAIN rate
    never pass it, regardless of how many distinct ".com" names get pooled
    into one group. No public-suffix-list dependency, deliberately,
    matching this project's established GeoIP/host-identity stub precedent
    (see [[geoip-resolver-stub]]/[[host-identity-stub]] in TODO.md's
    Architecture Decisions Tracker).
    """
    labels = query_name.lower().rstrip(".").split(".")
    return labels[-1] if labels else query_name.lower()


def _registrable_label(query_name: str) -> str:
    """Everything except the rightmost label — the part whose randomness
    (or lack of it) actually distinguishes a DGA-cycled candidate name
    ("xk29fh3mdq7z") from a real word ("google") or a real multi-label
    hostname ("outlook.office365").
    """
    labels = query_name.lower().rstrip(".").split(".")
    return ".".join(labels[:-1])


def _shannon_entropy(label: str) -> float:
    """Bits per character. A real word ("cdn-update-service") sits well
    under 3.5 (repeated, low-variety characters); a random-looking DGA/
    tunneling-encoded label ("xk29fh3mdq7z") sits close to log2(alphabet
    size), typically 3.5+ for a 10+ char alphanumeric string.
    """
    if not label:
        return 0.0
    counts = Counter(label)
    length = len(label)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


class DNSTunnelingRule(DetectionRule):
    rule_key = "dns_tunneling"
    name = "DNS Tunneling / Beaconing"
    description = (
        "Many distinct names queried under one TLD or pseudo-TLD, from one "
        "resolver, within a short window, combined with either a high "
        "NXDOMAIN rate or high-entropy (random-looking) labels — the "
        "query-name encoding and rapid-fire lookup pattern typical of DNS "
        "tunneling (subdomains under one owned domain) or domain-generation-"
        "algorithm beaconing (many distinct look-alike candidate domains), "
        "not normal browsing traffic."
    )
    category = DetectionCategory.NETWORK
    default_severity = Severity.MEDIUM
    source_types = (SourceType.DNS,)
    default_config = {
        "min_distinct_names": 3,
        "window_seconds": 300,
        "nxdomain_ratio_threshold": 0.3,
        "entropy_threshold": 3.3,
    }
    mitre_technique_ids = ("T1071.004",)

    def evaluate(
        self, db: Session, events: Sequence[SecurityEvent], config: dict
    ) -> list[RuleFinding]:
        min_distinct = config.get("min_distinct_names", self.default_config["min_distinct_names"])
        window_seconds = config.get("window_seconds", self.default_config["window_seconds"])
        nx_threshold = config.get(
            "nxdomain_ratio_threshold", self.default_config["nxdomain_ratio_threshold"]
        )
        entropy_threshold = config.get(
            "entropy_threshold", self.default_config["entropy_threshold"]
        )

        # Grouped by (resolver, suffix) — DNS events carry no client host
        # field (only the resolver that logged the query), so the resolver
        # is the closest available grouping key to "one source of
        # activity." See DEF.md § Phase 3 for the DNS schema.
        by_group: dict[tuple[str, str], list[SecurityEvent]] = defaultdict(list)
        for event in events:
            query_name = event.normalized.get("query_name")
            resolver_ip = event.normalized.get("resolver_ip")
            if not query_name or not resolver_ip:
                continue
            by_group[(resolver_ip, _registry_suffix(query_name))].append(event)

        findings: list[RuleFinding] = []
        for (resolver_ip, suffix), group_events in by_group.items():
            group_events.sort(key=lambda e: e.occurred_at)

            best_matched: list[SecurityEvent] = []
            best_distinct = 0
            left = 0
            for right in range(len(group_events)):
                while (
                    group_events[right].occurred_at - group_events[left].occurred_at
                ).total_seconds() > window_seconds:
                    left += 1
                window = group_events[left : right + 1]
                distinct_names = {e.normalized.get("query_name", "").lower() for e in window}
                if len(distinct_names) > best_distinct:
                    best_distinct = len(distinct_names)
                    best_matched = window

            if best_distinct < min_distinct:
                continue

            nx_count = sum(
                1 for e in best_matched if e.normalized.get("response_code") == "NXDOMAIN"
            )
            nxdomain_ratio = nx_count / len(best_matched)
            entropies = [
                _shannon_entropy(_registrable_label(e.normalized.get("query_name", "")))
                for e in best_matched
            ]
            avg_entropy = sum(entropies) / len(entropies) if entropies else 0.0

            if nxdomain_ratio < nx_threshold and avg_entropy < entropy_threshold:
                continue

            first_event_at = best_matched[0].occurred_at
            last_event_at = best_matched[-1].occurred_at
            severity, factors = score_severity(self.default_severity, best_distinct, min_distinct)

            signals = []
            if nxdomain_ratio >= nx_threshold:
                signals.append(f"{nxdomain_ratio:.0%} NXDOMAIN")
            if avg_entropy >= entropy_threshold:
                signals.append(f"avg label entropy {avg_entropy:.1f} bits/char")
            rationale = (
                f"{best_distinct} distinct names queried under .{suffix} via "
                f"resolver {resolver_ip!r} within "
                f"{(last_event_at - first_event_at).total_seconds():.0f}s "
                f"({', '.join(signals)})."
            )

            findings.append(
                RuleFinding(
                    matched_event_ids=[e.id for e in best_matched],
                    severity=severity,
                    confidence=0.65,
                    rationale=rationale,
                    severity_factors={
                        **factors,
                        "nxdomain_ratio": round(nxdomain_ratio, 2),
                        "avg_label_entropy": round(avg_entropy, 2),
                    },
                    first_event_at=first_event_at,
                    last_event_at=last_event_at,
                )
            )
        return findings
