from app.correlation.base import (
    AlertSignature,
    CorrelationConfig,
    IncidentSignature,
    ScoreBreakdown,
)


def _time_gap_seconds(alert_sig: AlertSignature, incident_sig: IncidentSignature) -> float:
    """0 if the alert's event range overlaps the incident's activity range;
    otherwise the gap between the nearest edges.
    """
    if incident_sig.first_activity_at is None or incident_sig.last_activity_at is None:
        return 0.0
    if (
        alert_sig.first_event_at <= incident_sig.last_activity_at
        and alert_sig.last_event_at >= incident_sig.first_activity_at
    ):
        return 0.0
    if alert_sig.first_event_at > incident_sig.last_activity_at:
        return (alert_sig.first_event_at - incident_sig.last_activity_at).total_seconds()
    return (incident_sig.first_activity_at - alert_sig.last_event_at).total_seconds()


def score_alert_against_incident(
    alert_sig: AlertSignature, incident_sig: IncidentSignature, config: CorrelationConfig
) -> ScoreBreakdown:
    gap_seconds = _time_gap_seconds(alert_sig, incident_sig)
    time_score = (
        config.time_weight * max(0.0, 1 - gap_seconds / config.time_decay_seconds)
        if config.time_decay_seconds
        else 0.0
    )

    shared_iocs = alert_sig.ioc_ids & incident_sig.ioc_ids
    ioc_score = config.ioc_weight * min(1.0, len(shared_iocs) / config.ioc_saturation)

    shared_hosts = alert_sig.host_entity_ids & incident_sig.host_entity_ids
    host_score = config.host_weight * min(1.0, len(shared_hosts) / config.host_saturation)

    shared_techniques = alert_sig.technique_ids & incident_sig.technique_ids
    mitre_score = config.mitre_weight * min(1.0, len(shared_techniques) / config.mitre_saturation)

    return ScoreBreakdown(
        time_score=time_score,
        ioc_score=ioc_score,
        host_score=host_score,
        mitre_score=mitre_score,
        shared_ioc_ids=shared_iocs,
        shared_host_ids=shared_hosts,
        shared_technique_ids=shared_techniques,
    )
