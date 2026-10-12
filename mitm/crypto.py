"""
Cryptography functionalities.
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import ssl
import tempfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

LRU_MAX_SIZE = 1024
"""
Number of per-host `ssl.SSLContext` objects cached by each `CertificateAuthority`.

Python's `ssl` module cannot load certificates from memory, so every new context costs
a round-trip through disk. Caching keeps that cost to once per host.
"""

CA_VALIDITY = datetime.timedelta(days=3650)
LEAF_VALIDITY = datetime.timedelta(days=365)  # Apple rejects leaf certs valid for over 825 days.


def new_key() -> rsa.RSAPrivateKey:
    """
    Generates a 2048-bit RSA private key.
    """
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class CertificateAuthority:
    """
    Certificate authority used to sign a certificate for every intercepted host.

    Example:

        .. code-block:: python

            from mitm import CertificateAuthority

            ca = CertificateAuthority()                   # New, in-memory CA.
            ca = CertificateAuthority.init(path)          # Load from `path`, or create and save it there.
            ca = CertificateAuthority.load(cert, key)     # Load from specific files.
    """

    def __init__(
        self,
        key: rsa.RSAPrivateKey | None = None,
        cert: x509.Certificate | None = None,
    ):
        """
        Initializes the certificate authority.

        Args:
            key: Private key of the CA. Generated if not provided.
            cert: Certificate of the CA. Generated (and self-signed with `key`) if not provided.
        """
        self.key = key or new_key()
        self.cert = cert or self.new_cert(self.key)
        self.leaf_key: rsa.RSAPrivateKey | None = None
        self.contexts: dict[str, ssl.SSLContext] = {}

    @staticmethod
    def new_cert(key: rsa.RSAPrivateKey) -> x509.Certificate:
        name = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "mitm"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "mitm"),
            ]
        )
        now = datetime.datetime.now(datetime.UTC)
        return (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + CA_VALIDITY)
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256())
        )

    @classmethod
    def init(cls, path: Path | str) -> CertificateAuthority:
        """
        Loads the CA stored in `path`, or creates and saves a new one there.

        A new CA is also created if the stored one has expired, or if its key and
        certificate do not belong together.

        Args:
            path: Directory holding `mitm.pem` and `mitm.key`.
        """
        path = Path(path)
        cert_path, key_path = path / "mitm.pem", path / "mitm.key"

        if cert_path.exists() and key_path.exists():
            ca = cls.load(cert_path=cert_path, key_path=key_path)
            now = datetime.datetime.now(datetime.UTC)
            if ca.cert.public_key() == ca.key.public_key() and ca.cert.not_valid_after_utc > now:
                return ca

        ca = cls()
        ca.save(cert_path=cert_path, key_path=key_path)
        return ca

    def new_X509(self, host: str) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:  # noqa: N802
        """
        Generates a certificate for `host`, signed by this CA.

        Args:
            host: Hostname or IP address to generate the certificate for.

        Returns:
            A tuple of the certificate and its private key.
        """
        try:
            san: x509.GeneralName = x509.IPAddress(ipaddress.ip_address(host))
        except ValueError:
            san = x509.DNSName(host)

        # One key is shared by all leaf certificates: generating RSA keys is slow.
        if self.leaf_key is None:
            self.leaf_key = new_key()

        now = datetime.datetime.now(datetime.UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host[:64])]))
            .issuer_name(self.cert.subject)
            .public_key(self.leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + LEAF_VALIDITY)
            .add_extension(x509.SubjectAlternativeName([san]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()),
                critical=False,
            )
            .sign(self.key, hashes.SHA256())
        )
        return cert, self.leaf_key

    def new_context(self, host: str) -> ssl.SSLContext:
        """
        Returns a server-side `ssl.SSLContext` presenting a certificate for `host`.
        Contexts are cached; see `LRU_MAX_SIZE`.

        Args:
            host: Hostname or IP address the context will impersonate.
        """
        if context := self.contexts.pop(host, None):
            self.contexts[host] = context  # Mark as most recently used.
            return context

        cert, key = self.new_X509(host)

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.set_alpn_protocols(["http/1.1"])

        # `ssl` cannot load certificates from memory: https://github.com/python/cpython/issues/60691
        with tempfile.TemporaryDirectory() as directory:
            cert_path, key_path = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(private_bytes(key))
            context.load_cert_chain(certfile=cert_path, keyfile=key_path)

        self.contexts[host] = context
        if len(self.contexts) > LRU_MAX_SIZE:
            del self.contexts[next(iter(self.contexts))]
        return context

    def save(self, cert_path: Path | str, key_path: Path | str):
        """
        Saves the CA certificate and private key to disk. The key is only readable by
        the current user.

        Args:
            cert_path: Path to the certificate file.
            key_path: Path to the key file.
        """
        cert_path, key_path = Path(cert_path), Path(key_path)
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.parent.mkdir(parents=True, exist_ok=True)

        cert_path.write_bytes(self.cert.public_bytes(serialization.Encoding.PEM))

        key_path.unlink(missing_ok=True)
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(private_bytes(self.key))

    @classmethod
    def load(cls, cert_path: Path | str, key_path: Path | str) -> CertificateAuthority:
        """
        Loads a CA certificate and private key from disk.

        Args:
            cert_path: Path to the certificate file.
            key_path: Path to the key file.
        """
        cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
        key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
        return cls(key, cert)


def private_bytes(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
