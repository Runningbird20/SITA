"""Parses real sshd auth-log messages into AuthIngestionAdapter's raw
shape — shared by the syslog UDP listener (RFC 5424-framed) and the
file-tail ingester (plain/BSD-style auth.log lines), which differ only in
how they extract a (hostname, msg) pair from one line of text before
handing it to `parse_ssh_auth_message()`. See DEF.md § Phase 2,
"Post-roadmap addition: real ingestion (syslog + file-tail)".

Deliberately scoped to what real sshd auth-log lines actually look like —
not a general syslog-to-any-source-type mapper. A line whose envelope or
message body isn't recognized returns None and is silently skipped by the
caller, never guessed at or fabricated.
"""

import re

_RFC5424_RE = re.compile(
    r"^<(?P<pri>\d{1,3})>(?P<version>\d+)\s+(?P<timestamp>\S+)\s+(?P<hostname>\S+)\s+"
    r"(?P<appname>\S+)\s+(?P<procid>\S+)\s+(?P<msgid>\S+)\s+"
    r"(?P<structured_data>-|\[.*?\])\s?(?P<msg>.*)$"
)

# Classic BSD/RFC 3164-style line, no year in the timestamp (that's the
# format most local auth.log files actually use) — e.g.
# "Jan 15 03:00:00 db01 sshd[1234]: Failed password for admin from 1.2.3.4 port 51234 ssh2"
_PLAIN_LOG_RE = re.compile(
    r"^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+(?P<hostname>\S+)\s+"
    r"(?P<appname>\S+?)(\[\d+\])?:\s+(?P<msg>.*)$"
)

_SSH_FAILED_RE = re.compile(
    r"Failed password for (?:invalid user )?(?P<username>\S+) from (?P<source_ip>\S+) port \d+"
)
_SSH_ACCEPTED_RE = re.compile(
    r"Accepted (?P<method>password|publickey|keyboard-interactive) for (?P<username>\S+) "
    r"from (?P<source_ip>\S+) port \d+"
)
_METHOD_MAP = {"password": "password", "publickey": "publickey", "keyboard-interactive": "mfa"}


def parse_rfc5424_envelope(line: str) -> dict | None:
    """Splits one RFC 5424-framed syslog line into its header fields plus
    MSG. None if the line doesn't match the RFC 5424 envelope at all —
    legacy RFC 3164 BSD-style syslog (the far more common real-world
    default) isn't an RFC 5424 envelope and is handled separately by
    extract_plain_log_fields(), not by this function.
    """
    match = _RFC5424_RE.match(line.strip())
    return match.groupdict() if match else None


def extract_plain_log_fields(line: str) -> dict | None:
    """Extracts (hostname, appname, msg) from a classic BSD-style
    auth.log line. The embedded timestamp is intentionally not parsed —
    it carries no year, and correctly inferring one (year rollover,
    non-UTC local time, clock skew between the log host and this one) is
    more complexity than a file-tail demo connector needs; callers use
    their own observation time instead (see file_tail.py).
    """
    match = _PLAIN_LOG_RE.match(line.strip())
    return match.groupdict() if match else None


def parse_ssh_auth_message(msg: str, hostname: str, timestamp: str) -> dict | None:
    """Maps a recognized sshd auth-log MSG body onto AuthIngestionAdapter's
    raw shape (timestamp/host/event_result/username/source_ip/auth_method).
    None for anything not recognized (a non-sshd app-name upstream should
    already have filtered this out, or an sshd message this parser has no
    pattern for, e.g. a session-opened/closed line rather than an auth
    attempt).
    """
    failed = _SSH_FAILED_RE.search(msg)
    if failed:
        return {
            "timestamp": timestamp,
            "host": hostname,
            "event_result": "failure",
            "username": failed.group("username"),
            "source_ip": failed.group("source_ip"),
            "auth_method": "password",
        }
    accepted = _SSH_ACCEPTED_RE.search(msg)
    if accepted:
        return {
            "timestamp": timestamp,
            "host": hostname,
            "event_result": "success",
            "username": accepted.group("username"),
            "source_ip": accepted.group("source_ip"),
            "auth_method": _METHOD_MAP[accepted.group("method")],
        }
    return None


def parse_rfc5424_line(line: str) -> dict | None:
    """End-to-end for the syslog listener: an RFC 5424 line -> an
    AuthIngestionAdapter raw dict, or None if the envelope, the app-name
    (must be sshd/ssh), or the message body isn't recognized.
    """
    fields = parse_rfc5424_envelope(line)
    if fields is None or fields["timestamp"] == "-":
        return None
    if fields["appname"].lower() not in {"sshd", "ssh"}:
        return None
    return parse_ssh_auth_message(fields["msg"], fields["hostname"], fields["timestamp"])
