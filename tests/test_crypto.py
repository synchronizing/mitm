import asyncio
import datetime
import ipaddress
import ssl
import stat
import tempfile
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID

from mitm import crypto


def test_new_RSA():
    key = crypto.new_RSA()
    assert isinstance(key, rsa.RSAPrivateKey)
    assert key.key_size == 2048


class Test_CertificateAuthority:
    def test_init(self, ca):
        assert isinstance(ca, crypto.CertificateAuthority)
        assert isinstance(ca.key, rsa.RSAPrivateKey)
        assert isinstance(ca.cert, x509.Certificate)

        # The certificate is a CA, and belongs to the key.
        constraints = ca.cert.extensions.get_extension_for_class(x509.BasicConstraints)
        assert constraints.critical
        assert constraints.value.ca
        assert ca.cert.public_key() == ca.key.public_key()

    def test_helper_init(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)

            # No cert exists in path. Creates and saves it.
            ca = crypto.CertificateAuthority.init(path)

            # Assert the files were created, and that the key is only readable by the user.
            assert (path / "mitm.pem").exists()
            assert (path / "mitm.key").exists()
            assert stat.S_IMODE((path / "mitm.key").stat().st_mode) == 0o600

            # Loads the cert from the path.
            assert crypto.CertificateAuthority.init(path).cert == ca.cert

    def test_helper_init_mismatched_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            crypto.CertificateAuthority.init(path)

            # Replaces the key with the key of another CA.
            other = crypto.CertificateAuthority()
            other.save(cert_path=path / "other.pem", key_path=path / "mitm.key")

            # A new CA is generated, since the cert and key do not match.
            ca = crypto.CertificateAuthority.init(path)
            assert ca.cert.public_key() == ca.key.public_key()

    def test_helper_init_expired(self, monkeypatch):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)

            # Creates a CA that expired an hour ago.
            validity = crypto.CA_VALIDITY
            monkeypatch.setattr(crypto, "CA_VALIDITY", datetime.timedelta(hours=-1))
            expired = crypto.CertificateAuthority.init(path)
            monkeypatch.setattr(crypto, "CA_VALIDITY", validity)

            # A new CA is generated, since the old one expired.
            assert crypto.CertificateAuthority.init(path).cert != expired.cert

    @pytest.mark.parametrize(
        "host, san",
        [
            ("example.com", x509.DNSName("example.com")),
            ("127.0.0.1", x509.IPAddress(ipaddress.ip_address("127.0.0.1"))),
        ],
    )
    def test_new_X509(self, ca, host, san):

        # Creates signed cert.
        cert, key = ca.new_X509(host)
        assert cert.issuer == ca.cert.subject
        assert cert.public_key() == key.public_key()

        # Checks the cert is valid for the host, and for TLS servers.
        assert list(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value) == [san]
        assert ExtendedKeyUsageOID.SERVER_AUTH in cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value

        # Checks the cert is not valid for longer than Apple devices accept.
        assert cert.not_valid_after_utc - cert.not_valid_before_utc <= datetime.timedelta(days=398)

    def test_new_X509_long_hostname(self, ca):

        # The common name is limited to 64 characters, but hostnames can be longer.
        cert = ca.new_X509("a" * 60 + ".example.com")[0]
        assert cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)

    def test_new_context(self, ca, monkeypatch):
        monkeypatch.setattr(crypto, "LRU_MAX_SIZE", 2)
        certificate_authority = crypto.CertificateAuthority(ca.key, ca.cert)

        # Creates a new SSL context, and returns the same one after.
        context = certificate_authority.new_context("a.test")
        assert isinstance(context, ssl.SSLContext)
        assert certificate_authority.new_context("a.test") is context

        # Removes the least recently used context.
        certificate_authority.new_context("b.test")
        certificate_authority.new_context("c.test")
        assert list(certificate_authority.contexts) == ["b.test", "c.test"]

    @pytest.mark.asyncio
    async def test_new_context_handshake(self, ca, ca_file):

        # Starts a TLS server with a cert for 'localhost'.
        server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0, ssl=ca.new_context("localhost"))
        port = server.sockets[0].getsockname()[1]

        # A client that trusts the CA accepts the cert.
        context = ssl.create_default_context(cafile=ca_file)
        writer = (await asyncio.open_connection("127.0.0.1", port, ssl=context, server_hostname="localhost"))[1]
        assert writer.get_extra_info("peercert")["subject"] == ((("commonName", "localhost"),),)

        writer.close()
        server.close()
        await server.wait_closed()
