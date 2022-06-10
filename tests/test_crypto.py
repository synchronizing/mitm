import ssl
import tempfile
from pathlib import Path

import OpenSSL
from mitm import crypto


def test_new_RSA():
    key = crypto.new_RSA()
    assert isinstance(key, OpenSSL.crypto.PKey)


def test_new_X509():
    cert = crypto.new_X509()
    assert isinstance(cert, OpenSSL.crypto.X509)


class Test_CertificateAuthority:
    def test_init(self):
        ca = crypto.CertificateAuthority()
        assert isinstance(ca, crypto.CertificateAuthority)
        assert isinstance(ca.key, OpenSSL.crypto.PKey)
        assert isinstance(ca.cert, OpenSSL.crypto.X509)

    def test_helper_init(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)

            # No cert exists in path. Creates and saves it.
            ca = crypto.CertificateAuthority.init(path)
            assert isinstance(ca, crypto.CertificateAuthority)
            assert isinstance(ca.key, OpenSSL.crypto.PKey)
            assert isinstance(ca.cert, OpenSSL.crypto.X509)

            # Assert the files were created.
            pem = path / "mitm.pem"
            key = path / "mitm.key"

            assert pem.exists()
            assert key.exists()

            # Loads the cert from the path.
            ca = crypto.CertificateAuthority.init(path)
            assert isinstance(ca, crypto.CertificateAuthority)
            assert isinstance(ca.key, OpenSSL.crypto.PKey)
            assert isinstance(ca.cert, OpenSSL.crypto.X509)

    def test_new_X509(self):

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            ca = crypto.CertificateAuthority.init(path)

            # Creates signed cert.
            cert, key = ca.new_X509("example.com")

            assert isinstance(cert, OpenSSL.crypto.X509)
            assert isinstance(cert.get_pubkey(), OpenSSL.crypto.PKey)
            assert isinstance(key, OpenSSL.crypto.PKey)

            # Creates signed cert.
            cert, key = ca.new_X509("127.0.0.1")

            assert isinstance(cert, OpenSSL.crypto.X509)
            assert isinstance(cert.get_pubkey(), OpenSSL.crypto.PKey)
            assert isinstance(key, OpenSSL.crypto.PKey)

    def test_new_context(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            ca = crypto.CertificateAuthority.init(path)

            # Creates a new SSL context.
            context = ca.new_context("example.com")
            assert isinstance(context, ssl.SSLContext)
