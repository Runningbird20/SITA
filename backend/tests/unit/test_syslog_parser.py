from app.ingestion.syslog_parser import (
    extract_plain_log_fields,
    parse_rfc5424_envelope,
    parse_rfc5424_line,
    parse_ssh_auth_message,
)


class TestParseRfc5424Envelope:
    def test_splits_a_well_formed_line(self):
        line = (
            "<34>1 2026-01-15T03:00:00.000Z db01.internal sshd 1234 - - "
            "Failed password for admin from 198.51.100.1 port 51234 ssh2"
        )
        fields = parse_rfc5424_envelope(line)
        assert fields["hostname"] == "db01.internal"
        assert fields["appname"] == "sshd"
        assert fields["msg"] == "Failed password for admin from 198.51.100.1 port 51234 ssh2"

    def test_returns_none_for_a_non_rfc5424_line(self):
        assert parse_rfc5424_envelope("not a syslog line at all") is None


class TestParseSshAuthMessage:
    def test_failed_password(self):
        event = parse_ssh_auth_message(
            "Failed password for admin from 198.51.100.1 port 51234 ssh2",
            "db01.internal",
            "2026-01-15T03:00:00Z",
        )
        assert event == {
            "timestamp": "2026-01-15T03:00:00Z",
            "host": "db01.internal",
            "event_result": "failure",
            "username": "admin",
            "source_ip": "198.51.100.1",
            "auth_method": "password",
        }

    def test_failed_password_invalid_user(self):
        event = parse_ssh_auth_message(
            "Failed password for invalid user root from 203.0.113.9 port 22 ssh2",
            "db01.internal",
            "2026-01-15T03:00:00Z",
        )
        assert event["username"] == "root"
        assert event["event_result"] == "failure"

    def test_accepted_publickey(self):
        event = parse_ssh_auth_message(
            "Accepted publickey for jsmith from 10.0.0.9 port 51235 ssh2",
            "db01.internal",
            "2026-01-15T03:00:05Z",
        )
        assert event["event_result"] == "success"
        assert event["auth_method"] == "publickey"

    def test_accepted_keyboard_interactive_maps_to_mfa(self):
        event = parse_ssh_auth_message(
            "Accepted keyboard-interactive for jsmith from 10.0.0.9 port 51235 ssh2",
            "db01.internal",
            "2026-01-15T03:00:05Z",
        )
        assert event["auth_method"] == "mfa"

    def test_unrecognized_message_returns_none(self):
        assert parse_ssh_auth_message("pam_unix(sshd:session): session opened", "db01", "x") is None


class TestParseRfc5424Line:
    def test_end_to_end_ssh_message(self):
        line = (
            "<34>1 2026-01-15T03:00:00.000Z db01.internal sshd 1234 - - "
            "Failed password for admin from 198.51.100.1 port 51234 ssh2"
        )
        event = parse_rfc5424_line(line)
        assert event["username"] == "admin"
        assert event["host"] == "db01.internal"

    def test_non_sshd_appname_is_ignored(self):
        line = "<34>1 2026-01-15T03:00:00.000Z db01.internal cron 1234 - - some cron message"
        assert parse_rfc5424_line(line) is None

    def test_nilvalue_timestamp_is_ignored(self):
        line = "<34>1 - db01.internal sshd 1234 - - Failed password for admin from 1.2.3.4 port 22 ssh2"
        assert parse_rfc5424_line(line) is None

    def test_malformed_line_returns_none(self):
        assert parse_rfc5424_line("garbage") is None


class TestExtractPlainLogFields:
    def test_extracts_hostname_appname_and_msg(self):
        line = (
            "Jan 15 03:00:00 db01 sshd[1234]: Failed password for admin from 1.2.3.4 port 22 ssh2"
        )
        fields = extract_plain_log_fields(line)
        assert fields["hostname"] == "db01"
        assert fields["appname"] == "sshd"
        assert fields["msg"] == "Failed password for admin from 1.2.3.4 port 22 ssh2"

    def test_returns_none_for_an_unrecognized_line(self):
        assert extract_plain_log_fields("not a log line") is None
