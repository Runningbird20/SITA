"""A deliberately minimal hostname <-> IP identity bridge.

`auth`/`endpoint`/`web`/`dns` events identify a host by hostname;
`network` events identify it by IP. Nothing else in the system ties these
two representations of the same physical host together — a real
deployment would resolve this via a CMDB or asset inventory, which this
project doesn't have and isn't adding as a required dependency. This map
covers only the hosts this project's own scenario dataset deliberately
ties together (see data/synthetic_events/scenarios/
brute_force_to_lateral_movement/README.md) — a known, explicit stub, in
the same spirit as Phase 3's StaticGeoIPResolver. See DEF.md § Phase 5 and
the `[[host-identity-stub]]` entry in TODO.md's Architecture Decisions.
"""

KNOWN_HOST_ALIASES: dict[str, str] = {
    "web01.internal": "10.0.0.5",
    "ws-07.internal": "10.0.0.7",
}

_IP_TO_HOSTNAME: dict[str, str] = {ip: hostname for hostname, ip in KNOWN_HOST_ALIASES.items()}


def canonical_host(identifier: str) -> str:
    """Resolve a hostname or (if known) an aliased IP to the canonical
    hostname identity. Unknown identifiers pass through unchanged.
    """
    return _IP_TO_HOSTNAME.get(identifier, identifier)
