"""
Man-in-the-middle proxy for HTTP and HTTPS.

Github: https://github.com/synchronizing/mitm
Docs: https://synchronizing.github.io/mitm/
"""

__author__ = "Felipe Faria"
__project__ = "mitm"

import pathlib
from importlib import metadata

import platformdirs

try:
    __version__ = metadata.version(__project__)
except metadata.PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__data__ = pathlib.Path(platformdirs.user_data_dir(__project__, __author__))
"""
Directory where the certificate authority (``mitm.pem`` and ``mitm.key``) is stored.
"""

from mitm import crypto, http  # noqa: E402
from mitm.crypto import CertificateAuthority  # noqa: E402
from mitm.extension import middleware, protocol  # noqa: E402
from mitm.extension.middleware import HTTPLog, Log  # noqa: E402
from mitm.extension.protocol import HTTP  # noqa: E402
from mitm.models import Connection, Flow, Host, InvalidProtocol, Middleware, Protocol  # noqa: E402
from mitm.proxy import MITM  # noqa: E402

__all__ = [
    "HTTP",
    "MITM",
    "CertificateAuthority",
    "Connection",
    "Flow",
    "HTTPLog",
    "Host",
    "InvalidProtocol",
    "Log",
    "Middleware",
    "Protocol",
    "crypto",
    "http",
    "middleware",
    "protocol",
]
