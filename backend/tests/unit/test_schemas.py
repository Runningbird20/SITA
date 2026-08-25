from datetime import UTC, datetime

from app.models.enums import DetectionCategory, Severity
from app.schemas import DetectionRead

NOW = datetime.now(UTC)


def test_detection_read_validates_from_orm_like_object():
    class FakeORMDetection:
        id = "12345678-1234-5678-1234-567812345678"
        rule_key = "ssh_brute_force"
        name = "SSH Brute Force"
        description = "..."
        category = DetectionCategory.AUTHENTICATION
        default_severity = Severity.HIGH
        enabled = True
        config = None
        created_at = NOW

    schema = DetectionRead.model_validate(FakeORMDetection())
    assert schema.rule_key == "ssh_brute_force"
    assert schema.category is DetectionCategory.AUTHENTICATION
