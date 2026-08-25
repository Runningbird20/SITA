"""A deliberately minimal GeoIP resolver for the `impossible_travel` rule.

This is a known stub, not a real geolocation capability — see DEF.md § Phase 3
and the `[[geoip-resolver-stub]]` entry in TODO.md's Architecture Decisions.
`StaticGeoIPResolver` only knows about the IP addresses that actually appear
in this project's synthetic datasets. A real deployment would swap in a
different `GeoIPResolver` implementation (e.g. backed by a local MaxMind
GeoLite2 snapshot) behind this same interface — no paid/rate-limited API,
per the project's "no paid APIs" rule.
"""

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class GeoLocation:
    latitude: float
    longitude: float
    label: str


class GeoIPResolver(ABC):
    @abstractmethod
    def resolve(self, ip: str) -> GeoLocation | None:
        """Return a location for `ip`, or None if unknown — an unresolvable
        IP is silently skipped by callers, never treated as suspicious by
        omission.
        """


# Internal addresses all resolve to one fixed "home base" location; a
# handful of external addresses used across the synthetic datasets resolve
# to fictional-but-fixed distant regions, specifically to make the
# impossible-travel scenario fixture computable.
_KNOWN_LOCATIONS: dict[str, GeoLocation] = {
    "10.0.0.42": GeoLocation(38.9072, -77.0369, "Local Office (US-East)"),
    "10.0.0.51": GeoLocation(38.9072, -77.0369, "Local Office (US-East)"),
    "10.0.0.9": GeoLocation(38.9072, -77.0369, "Local Office (US-East)"),
    "203.0.113.7": GeoLocation(55.7558, 37.6173, "Test Region A (Moscow-area coordinates)"),
    "198.51.100.23": GeoLocation(-33.8688, 151.2093, "Test Region B (Sydney-area coordinates)"),
    "198.51.100.88": GeoLocation(35.6762, 139.6503, "Test Region C (Tokyo-area coordinates)"),
}


class StaticGeoIPResolver(GeoIPResolver):
    def resolve(self, ip: str) -> GeoLocation | None:
        return _KNOWN_LOCATIONS.get(ip)


def haversine_km(a: GeoLocation, b: GeoLocation) -> float:
    """Great-circle distance between two points, in kilometers."""
    earth_radius_km = 6371.0
    lat1, lon1, lat2, lon2 = map(math.radians, [a.latitude, a.longitude, b.latitude, b.longitude])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * earth_radius_km * math.asin(math.sqrt(h))
