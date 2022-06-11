__author__ = "Felipe Faria"
__project__ = "mitm"

import pathlib
import appdirs
from pbr.version import VersionInfo

__version__ = VersionInfo(__project__).release_string()
__data__ = pathlib.Path(appdirs.user_data_dir(__package__, __author__))

import logging
import sys

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

from mitm.core import *
from mitm.crypto import *
from mitm.extension import *
from mitm.mitm import *

__all__ = [
    "Host",
    "Connection",
    "Flow",
    "MITM",
    "Middleware",
    "Protocol",
    "InvalidProtocol",
    "CertificateAuthority",
]
