"""One-page-ish PDF report for an incident — resolves WHATNEXT.md's
"Export" item. See DEF.md § Phase 9, "Post-roadmap addition: incident
export (CSV/PDF)".

fpdf2: pure-Python, no system dependency (no wkhtmltopdf/Chromium the way
weasyprint/Playwright-based PDF generation would need), MIT-licensed —
the one new dependency this feature needed, justified by there being no
stdlib way to produce a real PDF. AI-generated content is visually
distinguishable (a labeled "AI Analysis" section, clearly separate from
the deterministic alert/IOC tables above it) — the same "never merge
LLM output into deterministic fields, always distinguishable" principle
the dashboard's own AI panel already follows.

Two real bugs, both caught by actually exporting a real generated
incident, not assumed:
1. fpdf2's built-in core fonts only encode latin-1, but this project's
   own generated incident titles use "→" (correlation's title generator
   joins alert names with " → "), which crashed export with a
   UnicodeEncodeError. _safe() transliterates the specific "smart"
   typography this project's own generated text and the vendored MITRE
   descriptions actually contain, falling back to `?` for anything else.
2. fpdf2's `cell()`/`multi_cell()` default to *not* resetting the X
   cursor to the left margin (`ln=True` is deprecated and doesn't do
   this reliably either) — after any call without an explicit
   `new_x=XPos.LMARGIN, new_y=YPos.NEXT`, the cursor was left near the
   right edge of the page, so the next full-width (`w=0`) call had
   almost no horizontal space left and raised
   `FPDFException: Not enough horizontal space to render a single
   character`. `_line()` below is the one place that sets this
   correctly, used for every text block instead of calling fpdf2's
   methods directly.
"""

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.models.incident import Incident

_TRANSLATIONS = {
    "→": "->",  # →
    "—": "--",  # —
    "–": "-",  # –
    "‘": "'",  # '
    "’": "'",  # '
    "“": '"',  # "
    "”": '"',  # "
}


def _safe(text: str) -> str:
    for char, replacement in _TRANSLATIONS.items():
        text = text.replace(char, replacement)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _line(pdf: FPDF, text: str, size: float = 10, bold: bool = False, height: float = 5) -> None:
    pdf.set_font("Helvetica", "B" if bold else "", size)
    pdf.multi_cell(0, height, _safe(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


class _IncidentReportPDF(FPDF):
    def header(self) -> None:
        _line(self, "SITA Incident Report", size=14, bold=True, height=8)
        self.set_text_color(120, 120, 120)
        _line(self, "Deterministic findings and AI-assisted analysis, clearly separated", size=9)
        self.set_text_color(0, 0, 0)
        self.ln(2)


def _section_heading(pdf: FPDF, text: str) -> None:
    _line(pdf, text, size=12, bold=True, height=8)


def export_incident_pdf(incident: Incident) -> bytes:
    pdf = _IncidentReportPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    _line(pdf, incident.title or "(untitled incident)", size=13, bold=True, height=7)
    _line(pdf, f"Status: {incident.status}    Severity: {incident.severity}", height=6)
    _line(
        pdf,
        f"Activity window: {incident.first_activity_at.isoformat()} to "
        f"{incident.last_activity_at.isoformat()}",
        height=6,
    )
    pdf.ln(4)

    _section_heading(pdf, f"Alerts ({len(incident.alerts)})")
    if not incident.alerts:
        _line(pdf, "None.")
    for alert in incident.alerts:
        _line(pdf, f"[{alert.severity}] {alert.detection.name}", bold=True, height=6)
        _line(pdf, alert.rationale, size=9)
        pdf.ln(1)
    pdf.ln(3)

    iocs = {ioc.id: ioc for alert in incident.alerts for ioc in alert.iocs}
    _section_heading(pdf, f"IOCs ({len(iocs)})")
    if not iocs:
        _line(pdf, "None.")
    for ioc in iocs.values():
        _line(pdf, f"{ioc.ioc_type}: {ioc.value}", size=9)
    pdf.ln(3)

    recommendations = list(incident.recommendations)
    _section_heading(pdf, f"Recommendations ({len(recommendations)})")
    if not recommendations:
        _line(pdf, "None.")
    for rec in recommendations:
        _line(pdf, f"[{rec.priority}] {rec.text}", size=9)
    pdf.ln(3)

    # AI-generated content, deliberately last and clearly labeled — never
    # presented as if it were a deterministic finding above it.
    summaries = [r for r in incident.analysis_results if r.task_type == "incident_summary"]
    if summaries:
        _section_heading(pdf, "AI Analysis (assistive, not a deterministic finding)")
        latest = max(summaries, key=lambda r: r.created_at)
        text = latest.parsed_output.get("summary", "") if latest.parsed_output else ""
        _line(pdf, text or "(no summary available)", size=9)

    return bytes(pdf.output())
