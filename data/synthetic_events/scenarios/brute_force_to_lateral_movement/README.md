# Scenario: `brute_force_to_lateral_movement`

A four-source-type, single-narrative attack, designed as the primary end-to-end demo dataset — the same story Phase 5's correlation engine is meant to reconstruct as **one incident**, and the same story later phases can use as a labeled evaluation fixture with a known expected outcome (Phase 12).

## Storyline

All times UTC, 2026-01-15.

| Time | Source | What happens |
|---|---|---|
| 03:10:00 – 03:13:15 | `auth.jsonl` | An external attacker (`203.0.113.7`) attempts SSH password logins as `root` against `web01.internal` — 14 failures at 15-second intervals. |
| 03:13:30 | `auth.jsonl` | The 15th attempt succeeds. `web01.internal` is compromised. |
| 03:16:00 – 03:16:40 | `network.jsonl` | From `web01.internal`'s internal address (`10.0.0.5`, now attacker-controlled), a fast internal port scan probes `ws-07.internal` (`10.0.0.7`) across 9 ports. The last connection (RDP, port 3389) actually completes with real byte transfer — the attacker found a way in. |
| 03:18:00 – 03:18:22 | `endpoint.jsonl` | On `ws-07.internal`, under the `svc-web` account: a `whoami` recon command, then an obfuscated (base64-encoded) PowerShell download-cradle command, then a `rundll32.exe` execution of a dropped payload — a classic download-and-execute chain. |
| 03:18:30 – 03:18:45 | `dns.jsonl` | From `ws-07.internal`: two DGA-pattern NXDOMAIN lookups, then a successful `TXT` and `A` record lookup for `cdn-update-service.example` — a plausible C2 check-in/beacon pattern (`TXT` queries are a common DNS-tunneling channel). |

## What ties it together (for Phase 5 correlation)

- **Shared entity `web01.internal` / `10.0.0.5`** links the `auth` stage to the `network` stage (the compromised host becomes the attacker's pivot point).
- **Shared entity `ws-07.internal` / `10.0.0.7`** links the `network` stage to the `endpoint` and `dns` stages (the scanned-then-accessed host is where the payload actually runs and beacons out).
- **Time window**: the whole scenario spans under 9 minutes, well within any reasonable correlation window.

A correlation engine using shared-IP/shared-host signals within a time window should be able to reconstruct all four stages as one incident — scattered across four independently-ingested files, but describing one continuous compromise.

## Expected detections (Phase 3) and MITRE mappings (Phase 8)

| Stage | Expected detection rule | Expected MITRE technique |
|---|---|---|
| `auth.jsonl` | SSH brute force | T1110.001 (Password Guessing) / T1110 (Brute Force) |
| `network.jsonl` | Port scanning | T1046 (Network Service Discovery) |
| `endpoint.jsonl` | Suspicious PowerShell activity | T1059.001 (PowerShell) |
| `dns.jsonl` | (no dedicated Phase 3 rule yet — a candidate for a future DNS-tunneling/DGA rule) | T1071.004 (DNS) / T1568 (Dynamic Resolution) |

## Loading this scenario

```bash
cd backend
uv run python -m app.ingestion.cli auth ../data/synthetic_events/scenarios/brute_force_to_lateral_movement/auth.jsonl
uv run python -m app.ingestion.cli network ../data/synthetic_events/scenarios/brute_force_to_lateral_movement/network.jsonl
uv run python -m app.ingestion.cli endpoint ../data/synthetic_events/scenarios/brute_force_to_lateral_movement/endpoint.jsonl
uv run python -m app.ingestion.cli dns ../data/synthetic_events/scenarios/brute_force_to_lateral_movement/dns.jsonl
```

Each file gets its own `ingestion_batch_id`; the entities that tie them together (`web01.internal`, `10.0.0.5`, `ws-07.internal`, `10.0.0.7`) are what a correlation engine — not the ingestion layer — is responsible for connecting.
