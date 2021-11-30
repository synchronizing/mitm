"""
Cryptography functionalities for mitm.
"""

import pathlib
import random
import socket
import ssl
from typing import Optional, Tuple

from OpenSSL import crypto

from . import __data__


def new_RSA(bits: int = 2048) -> crypto.PKey:
    """Generates an RSA pair.

    This function is intended to be utilized with :py:func:`new_X509`. See function
    :py:func:`new_pair` to understand how to generate a valid RSA and X509 pair for
    SSL/TLS use.

    Args:
        bits: Size of the RSA key. Defaults to 2048.
    """

    rsa = crypto.PKey()
    rsa.generate_key(crypto.TYPE_RSA, bits)
    return rsa


def new_X509(
    country_name: str = "US",
    state_or_province_name: str = "New York",
    locality: str = "New York",
    organization_name: str = "mitm",
    organization_unit_name: str = "mitm",
    common_name: str = socket.gethostname(),
    serial_number: int = random.getrandbits(1024),
    time_not_before: int = 0,  # 0 means now.
    time_not_after: int = 5 * (365 * 24 * 60 * 60),  # 5 year.
) -> crypto.X509:
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
        serial_number: A unique serial number. Any number between 0 and 2^159-1. Defaults to random number.
        time_not_before: Time since cert is valid. 0 means now. Defaults to ``0``.
        time_not_after: Time when cert is no longer valid. Defaults to 5 years.
    """

    cert = crypto.X509()
    cert.get_subject().C = country_name
    cert.get_subject().ST = state_or_province_name
    cert.get_subject().L = locality
    cert.get_subject().O = organization_name
    cert.get_subject().OU = organization_unit_name
    cert.get_subject().CN = common_name
    cert.set_serial_number(serial_number)
    cert.gmtime_adj_notBefore(time_not_before)
    cert.gmtime_adj_notAfter(time_not_after)
    cert.set_issuer(cert.get_subject())
    return cert


def new_pair(
    key_path: Optional[pathlib.Path] = None,
    cert_path: Optional[pathlib.Path] = None,
) -> Tuple[bytes, bytes]:
    """
    Generates an RSA and self-signed X509 certificate for use with TLS/SSL.

    The X509 certificate is self-signed and is not signed by any other certificate
    authority, containing default values for its fields.

    Args:
        key_path: Optional path to save key.
        cert_path: Optional path to save cert.

    Returns:
        tuple: Key and certificate bytes ready to be saved.
    """

    rsa = new_RSA()
    cert = new_X509()

    # Sets the certificate public key, and signs it.
    cert.set_pubkey(rsa)
    cert.sign(rsa, "sha256")

    # Dumps the .crt and .key files as bytes.
    key = crypto.dump_privatekey(crypto.FILETYPE_PEM, rsa)
    crt = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

    # Stores they .crt and .key file if specified.
    if key_path:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        with key_path.open("wb") as file:
            file.write(key)
    if cert_path:
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        with cert_path.open("wb") as file:
            file.write(crt)

    return key, crt


def mitm_ssl_default_context() -> ssl.SSLContext:
    """
    Generates the default SSL context for `mitm`.
    """
    rsa_key, rsa_cert = __data__ / "mitm.key", __data__ / "mitm.crt"
    new_pair(key_path=rsa_key, cert_path=rsa_cert)
    context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
    context.load_cert_chain(certfile=rsa_cert, keyfile=rsa_key)
    return context
