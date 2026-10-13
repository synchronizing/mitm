"""
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
    # The package is not installed (e.g. running from the source directly).
    __version__ = "0.0.0"

__data__ = pathlib.Path(platformdirs.user_data_dir(__project__, __author__))

from mitm import crypto, http
from mitm.crypto import *
from mitm.extension import *
from mitm.models import *
from mitm.proxy import *

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
