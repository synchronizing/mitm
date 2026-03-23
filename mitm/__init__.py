"""
Github: https://github.com/synchronizing/mitm
Docs: https://synchronizing.github.io/mitm/
"""

__author__ = "Felipe Faria"
__project__ = "mitm"

import pathlib
from importlib import metadata

import appdirs

__version__ = metadata.version(__project__)
__data__ = pathlib.Path(appdirs.user_data_dir(__package__, __author__))

import logging
import sys

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

from mitm.extension import *
from mitm.models import *
from mitm.proxy import *
from mitm.utils import crypto
from mitm.utils.crypto import *

__all__ = [
    "MITM",
    "CertificateAuthority",
    "Connection",
    "Flow",
    "Host",
    "InvalidProtocol",
    "Middleware",
    "Protocol",
]
