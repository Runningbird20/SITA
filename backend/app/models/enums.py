"""Enum values for the core data model, per DEF.md.

Stored as VARCHAR (native_enum=False) rather than native Postgres enum types,
so SQLite dev/test parity holds and values can be extended via code + a plain
migration rather than `ALTER TYPE`.
"""

from enum import StrEnum


class SourceType(StrEnum):
    AUTH = "auth"
    ENDPOINT = "endpoint"
    NETWORK = "network"
    DNS = "dns"
    WEB = "web"


class EntityType(StrEnum):
    HOST = "host"
    USER = "user"
    IP = "ip"
    DOMAIN = "domain"


class EntityRole(StrEnum):
    SOURCE = "source"
    TARGET = "target"
    ACTOR = "actor"


class DetectionCategory(StrEnum):
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    ENDPOINT = "endpoint"
    WEB = "web"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(StrEnum):
    NEW = "new"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    CLOSED = "closed"


class IOCType(StrEnum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    DOMAIN = "domain"
    URL = "url"
    FILE_HASH_MD5 = "file_hash_md5"
    FILE_HASH_SHA1 = "file_hash_sha1"
    FILE_HASH_SHA256 = "file_hash_sha256"
    EMAIL = "email"
    USERNAME = "username"


class ExtractionSource(StrEnum):
    REGEX = "regex"
    LLM_ASSISTED = "llm_assisted"


class ValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIED = "unverified"


class MitreMappingSource(StrEnum):
    RULE = "rule"
    LLM = "llm"


class AnalysisTaskType(StrEnum):
    INCIDENT_SUMMARY = "incident_summary"
    SEVERITY_EXPLANATION = "severity_explanation"
    ATTACK_CLASSIFICATION = "attack_classification"
    INVESTIGATION_HYPOTHESIS = "investigation_hypothesis"
    INVESTIGATION_STEPS = "investigation_steps"
    MITRE_SUGGESTION = "mitre_suggestion"


class AnalysisValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    TIMEOUT = "timeout"
    PROVIDER_ERROR = "provider_error"


class RecommendationSource(StrEnum):
    RULE_BASED = "rule_based"
    LLM = "llm"


class RecommendationPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecommendationStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    DISMISSED = "dismissed"
    COMPLETED = "completed"


class FeedbackRating(StrEnum):
    UP = "up"
    DOWN = "down"


class UserRole(StrEnum):
    ANALYST = "analyst"
    ADMIN = "admin"
