"""Flat CSV export of one incident — resolves WHATNEXT.md's "Export"
item: no way to get an incident out as a report. See DEF.md § Phase 9,
"Post-roadmap addition: incident export (CSV/PDF)".

One row per alert (repeating the incident-level fields), the same
"flatten to rows" shape any SIEM/ticketing CSV import expects — an
incident with zero alerts still exports one row (all alert-level fields
blank), so the incident itself is never silently absent from the file.
Built from the real ORM Incident (not the API's IncidentDetail schema) so
the detection *name*, not just its id, is available without a second
lookup.
"""

import csv
import io

from app.models.incident import Incident

_FIELDS = [
    "incident_id",
    "incident_title",
    "incident_status",
    "incident_severity",
    "first_activity_at",
    "last_activity_at",
    "alert_id",
    "alert_detection",
    "alert_severity",
    "alert_confidence",
    "alert_rationale",
]


def export_incident_csv(incident: Incident) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_FIELDS)
    writer.writeheader()

    base_row = {
        "incident_id": str(incident.id),
        "incident_title": incident.title,
        "incident_status": str(incident.status),
        "incident_severity": str(incident.severity),
        "first_activity_at": incident.first_activity_at.isoformat(),
        "last_activity_at": incident.last_activity_at.isoformat(),
    }

    if not incident.alerts:
        writer.writerow(base_row)
    else:
        for alert in incident.alerts:
            writer.writerow(
                {
                    **base_row,
                    "alert_id": str(alert.id),
                    "alert_detection": alert.detection.name,
                    "alert_severity": str(alert.severity),
                    "alert_confidence": alert.confidence,
                    "alert_rationale": alert.rationale,
                }
            )

    return buffer.getvalue()
