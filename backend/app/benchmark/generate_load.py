"""Bulk-generates synthetic events for throughput/latency benchmarking —
deliberately not checked in (unlike data/eval/): this is disposable load,
regenerated fresh on every benchmark run, not a reviewable fixture. See
DEF.md § Phase 12.
"""

import random
from datetime import UTC, datetime, timedelta

_RNG_SEED = 20260301  # reproducible runs, not cryptographically random
BASE = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)


def _ts(offset_seconds: float) -> str:
    return (BASE + timedelta(seconds=offset_seconds)).isoformat().replace("+00:00", "Z")


def generate_auth_events(n: int, rng: random.Random) -> list[dict]:
    events = []
    hosts = [f"bench-host-{i}.internal" for i in range(20)]
    users = [f"user{i}" for i in range(50)]
    for i in range(n):
        # ~5% of events form small brute-force-shaped bursts so detection
        # has real work to do, not just pass over inert data.
        is_burst = rng.random() < 0.05
        ip = f"203.0.{rng.randint(113, 118)}.{rng.randint(1, 254)}"
        events.append(
            {
                "timestamp": _ts(i * 2 + (0 if not is_burst else rng.random())),
                "host": rng.choice(hosts),
                "event_result": "failure" if is_burst or rng.random() < 0.1 else "success",
                "username": rng.choice(users),
                "source_ip": ip,
                "auth_method": "password",
                "service": "sshd",
            }
        )
    return events


def generate_network_events(n: int, rng: random.Random) -> list[dict]:
    events = []
    for i in range(n):
        events.append(
            {
                "timestamp": _ts(i * 1.5),
                "host": "bench-fw.internal",
                "src_ip": f"198.51.{rng.randint(100, 110)}.{rng.randint(1, 254)}",
                "src_port": rng.randint(1024, 65535),
                "dst_ip": f"10.9.{rng.randint(0, 5)}.{rng.randint(1, 254)}",
                "dst_port": rng.choice([22, 80, 443, 3389, 5432, 8080]),
                "protocol": "tcp",
                "bytes_sent": rng.randint(40, 5000),
                "bytes_received": rng.randint(0, 20000),
            }
        )
    return events


def generate_endpoint_events(n: int, rng: random.Random) -> list[dict]:
    processes = ["explorer.exe", "chrome.exe", "outlook.exe", "cmd.exe", "powershell.exe"]
    events = []
    for i in range(n):
        proc = rng.choice(processes)
        cmdline = (
            f"{proc} -Command Get-Process"
            if proc == "powershell.exe" and rng.random() < 0.05
            else f'"{proc}"'
        )
        events.append(
            {
                "timestamp": _ts(i * 3),
                "host": f"bench-ws-{rng.randint(0, 30)}.internal",
                "process_name": proc,
                "command_line": cmdline,
                "pid": rng.randint(1000, 9000),
                "parent_pid": rng.randint(500, 999),
                "parent_process_name": "explorer.exe",
                "user": f"user{rng.randint(0, 50)}",
            }
        )
    return events


def generate_all(events_per_source: int) -> dict[str, list[dict]]:
    rng = random.Random(_RNG_SEED)
    return {
        "auth": generate_auth_events(events_per_source, rng),
        "network": generate_network_events(events_per_source, rng),
        "endpoint": generate_endpoint_events(events_per_source, rng),
    }
