"""
Cryptography functionalities.
"""

import datetime
import ipaddress
import os
import ssl
import tempfile
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

LRU_MAX_SIZE = 1024
"""
Max size of the LRU cache used by `CertificateAuthority.new_context()` method. Defaults
to 1024.

Due to limitations of the Python's SSL module we are unable to load certificates/keys
from memory; on every request we must dump the generated cert/key to disk and pass the
paths to the `ssl.SSLContext.load_cert_chain()` method. For a few requests this is not
an issue, but for a large quantity of requests this is a significant performance hit.

To mitigate this issue each `CertificateAuthority` caches the `ssl.SSLContext` it
generates for each host. `LRU_MAX_SIZE` defines the maximum number of cached
`ssl.SSLContext` that can be stored in memory at one time, per certificate authority.

    .. code-block:: python

        from mitm import crypto

        # Updates the maximum size of the LRU cache.
        crypto.LRU_MAX_SIZE = 2048
"""

CA_VALIDITY = datetime.timedelta(days=3650)
"""
How long a generated certificate authority is valid for. Defaults to 10 years.
"""

LEAF_VALIDITY = datetime.timedelta(days=365)
"""
How long the certificates generated for each host are valid for. Defaults to 1 year.

Note that Apple devices reject certificates that are valid for more than 825 days.
"""


def new_RSA(bits: int = 2048) -> rsa.RSAPrivateKey:
    """
    Generates an RSA private key.

    Args:
        bits: Size of the RSA key. Defaults to 2048.
    """
    return rsa.generate_private_key(public_exponent=65537, key_size=bits)


class CertificateAuthority:
    """
    Certificate Authority interface.

    Example:

        .. code-block:: python

            from mitm import CertificateAuthority

            # Generates a new certificate authority in memory.
            certificate_authority = CertificateAuthority()

            # Loads the certificate authority in 'path', or generates and saves one there.
            certificate_authority = CertificateAuthority.init(path)
    """

    def __init__(
        self,
        key: Optional[rsa.RSAPrivateKey] = None,
        cert: Optional[x509.Certificate] = None,
    ):
        """
        Generates a certificate authority.

        Args:
            key: Private key of the CA. Generated if not provided.
            cert: Certificate of the CA. Generated (and signed with the key) if not provided.
        """
        self.key = key if key else new_RSA()
        self.cert = cert if cert else self.new_cert(self.key)

        # Key shared by all of the certificates generated for each host. Generating a new
        # RSA key for every host is slow, so one is generated the first time it is needed.
        self.leaf_key: Optional[rsa.RSAPrivateKey] = None

        # Cache of 'ssl.SSLContext' generated for each host. See 'LRU_MAX_SIZE' above.
        self.contexts: Dict[str, ssl.SSLContext] = {}

    @staticmethod
    def new_cert(key: rsa.RSAPrivateKey) -> x509.Certificate:
        """
        Generates a self-signed certificate for the certificate authority.

        Args:
            key: Private key of the CA.
        """
        name = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, "mitm"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "mitm"),
            ]
        )

        # Creates CA.
        now = datetime.datetime.now(datetime.timezone.utc)
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
    def init(cls, path: Union[Path, str]) -> "CertificateAuthority":
        """
        Helper init method to initialize or load a CA.

        A new CA is generated if one does not exist in the path, if it has expired, or if
        its certificate and private key do not match.

        Args:
            path: The path where `mitm.pem` and `mitm.key` are to be loaded/saved.
        """
        path = Path(path)
        pem, key = path / "mitm.pem", path / "mitm.key"

        # Loads the CA, and checks that it is still usable.
        if pem.exists() and key.exists():
            certificate_authority = cls.load(cert_path=pem, key_path=key)
            matches = certificate_authority.cert.public_key() == certificate_authority.key.public_key()
            expired = certificate_authority.cert.not_valid_after_utc <= datetime.datetime.now(datetime.timezone.utc)
            if matches and not expired:
                return certificate_authority

        # Generates and saves a new CA.
        certificate_authority = cls()
        certificate_authority.save(cert_path=pem, key_path=key)
        return certificate_authority

    def new_X509(self, host: str) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """
        Generates a new certificate for the host.

        Note:
            The hostname must be a valid IP address or a valid hostname.

        Args:
            host: Hostname to generate the certificate for.

        Returns:
            A tuple of the certificate and private key.
        """

        # Generates the key shared by all hosts, if needed.
        if not self.leaf_key:
            self.leaf_key = new_RSA()

        # Sets the certificate 'subjectAltName' extension.
        try:
            san = x509.IPAddress(ipaddress.ip_address(host))
        except ValueError:
            san = x509.DNSName(host)

        # Generates new X509 certificate, signed with the CA's key. Note that the common
        # name is limited to 64 characters, but the 'subjectAltName' is not.
        now = datetime.datetime.now(datetime.timezone.utc)
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
        Generates a new SSLContext with a certificate for the given host.

        Args:
            host: Hostname to generate the context for.

        Returns:
            The SSLContext with the certificate loaded.
        """

        # Returns the cached context, and marks it as the most recently used.
        if host in self.contexts:
            self.contexts[host] = self.contexts.pop(host)
            return self.contexts[host]

        # Generates cert/key for the host.
        cert, key = self.new_X509(host)

        # Creates new SSLContext.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.set_alpn_protocols(["http/1.1"])

        # Store cert and key into file. Unfortunately we need to store them in disk
        # because SSLContext does not support loading from memory. This is a limitation
        # of the Python standard library, and the community: https://bugs.python.org/issue16487
        # Alternatives cannot be used for this because this context is eventually used
        # by `StreamWriter.start_tls(sslcontext=...)`, which only supports ssl.SSLContext.
        # The files are stored in a temporary directory only the user can read, and are
        # removed right after.
        with tempfile.TemporaryDirectory() as directory:
            cert_path, key_path = Path(directory) / "cert.pem", Path(directory) / "key.pem"
            cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
            key_path.write_bytes(private_bytes(key))
            context.load_cert_chain(certfile=cert_path, keyfile=key_path)

        # Caches the context, and removes the least recently used one if needed.
        self.contexts[host] = context
        if len(self.contexts) > LRU_MAX_SIZE:
            del self.contexts[next(iter(self.contexts))]

        return context

    def save(self, cert_path: Union[Path, str], key_path: Union[Path, str]):
        """
        Saves the certificate authority and its private key to disk.

        Note:
            The private key is only readable by the current user.

        Args:
            cert_path: Path to the certificate file.
            key_path: Path to the key file.
        """
        cert_path, key_path = Path(cert_path), Path(key_path)

        cert_path.parent.mkdir(parents=True, exist_ok=True)
        cert_path.write_bytes(self.cert.public_bytes(serialization.Encoding.PEM))

        # Creates the key file with the right permissions from the start.
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.unlink(missing_ok=True)
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(private_bytes(self.key))

    @classmethod
    def load(cls, cert_path: Union[Path, str], key_path: Union[Path, str]) -> "CertificateAuthority":
        """
        Loads the certificate authority and its private key from disk.

        Args:
            cert_path: Path to the certificate file.
            key_path: Path to the key file.
        """
        cert = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
        key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
        return cls(key, cert)


def private_bytes(key: rsa.RSAPrivateKey) -> bytes:
    """
    Dumps the private key in PEM format.

    Args:
        key: The private key to dump.
    """
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
