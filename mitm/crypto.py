"""
Module with crypto related functions.
"""

import random
import socket
from typing import Tuple

from OpenSSL import crypto


def new_RSA(bits: int = 1024) -> crypto.PKey:
    """Generates an RSA pair.

    Note:
        This function is intended to be utilized with :py:func:`new_X509`. See function
        :py:func:`new_pair` to understand how to generate a valid RSA and X509 pair for
        SSL/TLS use.

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

    Note:
        This function is intended to be utilized with :py:func:`new_RSA`. See function
        :py:func:`new_pair` to understand how to generate a valid RSA and X509 pair for
        SSL/TLS use.

    Args:
        country_name: Country name code.
        state_or_province_name: State or province name. Can be any.
        locality: Locality name. Can be any.
        organization_name: Name of the org generating the cert.
        organization_unit_name: Name of the subunit of the org generating cert.
        common_name: Server name protected by the SSL certificate.
        serial_number: A unique serial number. Any number between 0 and 2^159-1.
        time_not_before: Time for which certificate is valid from. 0 means now.
        time_not_after: Time for which certificate is not valid from. Defaults to 5 years.
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


def new_pair() -> Tuple[bytes, bytes]:
    """
    Generates an RSA and self-signed X509 certificate for use with TLS/SSL using the
    default mitm settings.

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

    return key, crt
