"""Shared types for IOC extraction. See DEF.md § Phase 4 for the full design."""

from dataclasses import dataclass

from app.models.enums import ExtractionSource, IOCType, ValidationStatus


@dataclass
class ExtractedIOC:
    ioc_type: IOCType
    value: str
    extraction_source: ExtractionSource
    validation_status: ValidationStatus
    confidence: float


# RFC 2606 / RFC 6762 special-use TLDs — never real indicators. Deliberately
# excludes "example": this project's own synthetic datasets use .example
# throughout (per that same RFC's convention) to represent externally-hosted
# malicious domains without pointing at a real one — filtering it out would
# make extraction unable to detect exactly the kind of domain its own
# fixtures are built to represent. See DEF.md § Phase 4.
RESERVED_TLDS = {"internal", "local", "test", "invalid", "localhost"}

# Common file extensions that would otherwise false-positive as domains —
# "payload.bin" and "powershell.exe" both match a plausible label.TLD shape.
# Not exhaustive; covers the extensions likely to appear in command lines
# and file paths within this project's scope.
NON_TLD_FILE_EXTENSIONS = {
    "exe",
    "bin",
    "dll",
    "bat",
    "cmd",
    "ps1",
    "sh",
    "py",
    "js",
    "txt",
    "log",
    "zip",
    "rar",
    "tmp",
    "dat",
    "cfg",
    "ini",
    "json",
    "xml",
    "csv",
    "doc",
    "docx",
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "db",
    "sql",
    "conf",
    "yml",
    "yaml",
}
