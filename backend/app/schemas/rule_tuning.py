from pydantic import BaseModel


class TuningSuggestionRead(BaseModel):
    rule_key: str
    rule_name: str
    total_alerts: int
    false_positive_count: int
    false_positive_rate: float
    threshold_key: str
    current_threshold_value: float
    suggested_threshold_value: float
    rationale: str
