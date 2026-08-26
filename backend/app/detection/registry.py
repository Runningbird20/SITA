from app.detection.anomalous_volume import AnomalousEventVolumeRule
from app.detection.base import DetectionRule
from app.detection.dns_tunneling import DNSTunnelingRule
from app.detection.impossible_travel import ImpossibleTravelRule
from app.detection.password_spraying import PasswordSprayingRule
from app.detection.port_scanning import PortScanningRule
from app.detection.repeated_auth_failures import RepeatedAuthFailuresRule
from app.detection.ssh_brute_force import SSHBruteForceRule
from app.detection.suspicious_auth_pattern import SuspiciousAuthPatternRule
from app.detection.suspicious_powershell import SuspiciousPowerShellRule

RULES: list[DetectionRule] = [
    SSHBruteForceRule(),
    PasswordSprayingRule(),
    SuspiciousAuthPatternRule(),
    PortScanningRule(),
    SuspiciousPowerShellRule(),
    ImpossibleTravelRule(),
    RepeatedAuthFailuresRule(),
    DNSTunnelingRule(),
    AnomalousEventVolumeRule(),
]

RULES_BY_KEY: dict[str, DetectionRule] = {rule.rule_key: rule for rule in RULES}
