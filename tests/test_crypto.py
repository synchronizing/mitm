import asyncio
import datetime
import ipaddress
import ssl
import stat

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtendedKeyUsageOID

from mitm import CertificateAuthority, crypto


class TestCertificateAuthority:
    def test_is_ca(self, ca):
        constraints = ca.cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert constraints.critical and constraints.value.ca
        assert ca.cert.public_key() == ca.key.public_key()

    def test_init_creates_then_loads(self, tmp_path):
        created = CertificateAuthority.init(tmp_path)
        loaded = CertificateAuthority.init(tmp_path)
        assert created.cert == loaded.cert
        assert stat.S_IMODE((tmp_path / "mitm.key").stat().st_mode) == 0o600

    def test_init_replaces_mismatched_key(self, tmp_path):
        CertificateAuthority.init(tmp_path)
        other = CertificateAuthority()
        other.save(cert_path=tmp_path / "other.pem", key_path=tmp_path / "mitm.key")
        replaced = CertificateAuthority.init(tmp_path)
        assert replaced.cert.public_key() == replaced.key.public_key()

    def test_init_replaces_expired(self, tmp_path, monkeypatch):
        validity = crypto.CA_VALIDITY
        monkeypatch.setattr(crypto, "CA_VALIDITY", datetime.timedelta(hours=-1))
        expired = CertificateAuthority.init(tmp_path)
        monkeypatch.setattr(crypto, "CA_VALIDITY", validity)
        assert CertificateAuthority.init(tmp_path).cert != expired.cert

    @pytest.mark.parametrize(
        ("host", "san"),
        [
            ("example.com", x509.DNSName("example.com")),
            ("127.0.0.1", x509.IPAddress(ipaddress.ip_address("127.0.0.1"))),
        ],
    )
    def test_new_x509(self, ca, host, san):
        cert, key = ca.new_X509(host)
        assert cert.issuer == ca.cert.subject
        assert cert.public_key() == key.public_key()
        assert list(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value) == [san]
        usage = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        assert ExtendedKeyUsageOID.SERVER_AUTH in usage
        assert cert.not_valid_after_utc - cert.not_valid_before_utc <= datetime.timedelta(days=398)

    def test_new_x509_long_hostname(self, ca):
        cert, _ = ca.new_X509("a" * 60 + ".example.com")
        assert cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)

    def test_new_context_cache(self, ca, monkeypatch):
        monkeypatch.setattr(crypto, "LRU_MAX_SIZE", 2)
        authority = CertificateAuthority(ca.key, ca.cert)
        first = authority.new_context("a.test")
        assert authority.new_context("a.test") is first
        authority.new_context("b.test")
        authority.new_context("c.test")
        assert list(authority.contexts) == ["b.test", "c.test"]

    async def test_new_context_handshake(self, ca, ca_file):
        """
        A client that trusts the CA accepts the generated certificate.
        """
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0, ssl=ca.new_context("localhost"))
        port = server.sockets[0].getsockname()[1]
        context = ssl.create_default_context(cafile=ca_file)
        writer = (await asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname="localhost"))[1]
        assert writer.get_extra_info("peercert")["subject"] == ((("commonName", "localhost"),),)
        writer.close()
        server.close()
        await server.wait_closed()
