"""
Cryptography functionalities.
"""
import random
import socket
import ssl
from pathlib import Path
from typing import Optional, Union

import OpenSSL

from mitm import __data__


def is_ip(host: str) -> bool:
    """
    Checks if the host is an IP address.

    Args:
        host: The hostname to check.

    Returns:
        ``True`` if the host is an IP address, ``False`` otherwise.
    """
    try:
        socket.inet_aton(host)
        return True
    except socket.error:
        return False


def new_RSA(bits: int = 2048) -> OpenSSL.crypto.PKey:
    """
    Generates an RSA pair.

    This function is intended to be utilized with :py:func:`new_X509`. See function
    :py:func:`new_pair` to understand how to generate a valid RSA and X509 pair for
    SSL/TLS use.

    Args:
        bits: Size of the RSA key. Defaults to 2048.
    """

    rsa = OpenSSL.crypto.PKey()
    rsa.generate_key(OpenSSL.crypto.TYPE_RSA, bits)
    return rsa


def new_X509(
    country_name: str = "US",
    state_or_province_name: str = "New York",
    locality: str = "New York",
    organization_name: str = "mitm",
    organization_unit_name: str = "mitm",
    common_name: str = "mitm",
    serial_number: int = random.randint(0, 2 ** 64 - 1),
    time_not_before: int = 0,  # 0 means now.
    time_not_after: int = 1 * (365 * 24 * 60 * 60),  # 1 year.
) -> OpenSSL.crypto.X509:
    """
    Generates a non-signed X509 certificate.

    This function is intended to be utilized with :py:func:`new_RSA`. See function
    :py:func:`new_pair` to understand how to generate a valid RSA and X509 pair for
    SSL/TLS use.

    Args:
        country_name: Country name code. Defaults to ``US``.
        state_or_province_name: State or province name. Defaults to ``New York``.
        locality: Locality name. Can be any. Defaults to ``New York``.
        organization_name: Name of the org generating the cert. Defaults to ``mitm``.
        organization_unit_name: Name of the subunit of the org. Defaults to ``mitm``.
        common_name: Server name protected by the SSL cert. Defaults to hostname.
        serial_number: A unique serial number. Any number between 0 and 2^64-1. Defaults to random number.
        time_not_before: Time since cert is valid. 0 means now. Defaults to ``0``.
        time_not_after: Time when cert is no longer valid. Defaults to 5 years.
    """

    cert = OpenSSL.crypto.X509()
    cert.get_subject().C = country_name
    cert.get_subject().ST = state_or_province_name
    cert.get_subject().L = locality
    cert.get_subject().O = organization_name
    cert.get_subject().OU = organization_unit_name
    cert.get_subject().CN = common_name
    cert.set_serial_number(serial_number)
    cert.set_version(2)
    cert.gmtime_adj_notBefore(time_not_before)
    cert.gmtime_adj_notAfter(time_not_after)
    cert.set_issuer(cert.get_subject())
    return cert


class CertificateAuthority:
    """
    Certificate Authority interface.
    """

    def __init__(
        self,
        key: Optional[OpenSSL.crypto.PKey] = None,
        cert: Optional[OpenSSL.crypto.X509] = None,
    ):
        """
        Generates a certificate authority.

        Args:
            key: Private key of the CA. Generated if not provided.
            cert: Unsigned certificate of the CA. Generated if not provided.
        """
        self.key = key if key else new_RSA()
        self.cert = cert if cert else new_X509(common_name="mitm")

        # Creates CA.
        self.cert.set_pubkey(self.key)
        self.cert.add_extensions(
            [
                OpenSSL.crypto.X509Extension(b"basicConstraints", True, b"CA:TRUE, pathlen:0"),
                OpenSSL.crypto.X509Extension(b"keyUsage", True, b"keyCertSign, cRLSign"),
                OpenSSL.crypto.X509Extension(b"subjectKeyIdentifier", False, b"hash", subject=self.cert),
            ],
        )
        self.cert.sign(self.key, "sha256")

    @classmethod
    def init(cls, path: Path):
        """
        Helper init method.

        Args:
            folder: The folder to initialize.
        """

        pem, key = path / "mitm.pem", path / "mitm.key"

        if not pem.exists() or not key.exists():
            ca = CertificateAuthority()
            ca.save(cert_path=pem, key_path=key)
        else:
            ca = CertificateAuthority.load(cert_path=pem, key_path=key)

        return ca

    def new_cert(self, host: str) -> OpenSSL.crypto.X509:
        """
        Generates a new certificate for the host.
        """

        # Generate a new key pair.
        key = new_RSA()

        # Generates new X509Request.
        req = OpenSSL.crypto.X509Req()
        req.get_subject().CN = host.encode("utf-8")
        req.set_pubkey(key)
        req.sign(key, "sha256")

        # Generates new X509 certificate.
        cert = new_X509(common_name=host)
        cert.set_issuer(self.cert.get_subject())
        cert.set_pubkey(req.get_pubkey())

        # Sets the certificate 'subjectAltName' extension.
        hosts = [f"DNS:{host}"]

        if is_ip(host):
            hosts += [f"IP:{host}"]
        else:
            hosts += [f"DNS:*.{host}"]

        hosts = ", ".join(hosts).encode("utf-8")
        cert.add_extensions([OpenSSL.crypto.X509Extension(b"subjectAltName", False, hosts)])

        # Sign the certificate.
        cert.sign(self.key, "sha256")

        return cert, key

    def save(self, cert_path: Union[Path, str], key_path: Union[Path, str]):
        """
        Saves the certificate authority and its private key to disk.

        Args:
            cert_path: Path to the certificate file.
            key_path: Path to the key file.
        """
        cert_path, key_path = Path(cert_path), Path(key_path)

        cert_path.parent.mkdir(parents=True, exist_ok=True)
        with cert_path.open("wb") as f:
            f.write(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, self.cert))

        key_path.parent.mkdir(parents=True, exist_ok=True)
        with key_path.open("wb") as f:
            f.write(OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, self.key))

    @classmethod
    def load(cls, cert_path: Union[Path, str], key_path: Union[Path, str]):
        """
        Loads the certificate authority and its private key from disk.

        Args:
            cert_path: Path to the certificate file.
            key_path: Path to the key file.
        """
        cert_path, key_path = Path(cert_path), Path(key_path)

        with cert_path.open("rb") as f:
            cert = OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM, f.read())

        with key_path.open("rb") as f:
            key = OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM, f.read())

        return cls(key, cert)


def new_context(cert: OpenSSL.crypto.X509, key: OpenSSL.crypto.PKey) -> ssl.SSLContext:
    """
    Creates a new SSLContext with the CA certificate.

    Args:
        cert_str: The certificate dump as a string.

    Returns:
        The SSLContext.
    """

    # Dump the cert and key.
    cert_dump = OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_PEM, cert)
    key_dump = OpenSSL.crypto.dump_privatekey(OpenSSL.crypto.FILETYPE_PEM, key)

    # Store cert and key into file. Unfortunately we need to store them in disk because
    # the SSLContext does not support loading from memory. This is a limitation of the
    # Python standard library. To speed things up we could implement this with a custom
    # package like M2Crypto, but that's a bit too much work for now.
    cert_path, key_path = __data__ / "temp.crt", __data__ / "temp.key"
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    with cert_path.open("wb") as f:
        f.write(cert_dump)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    with key_path.open("wb") as f:
        f.write(key_dump)

    # Creates new SSLContext.
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    # Remove the temporary files.
    cert_path.unlink()
    key_path.unlink()

    return context
