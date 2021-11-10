__project__ = "mitm"
__author__ = "Felipe Faria"

import logging
import sys

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)

from .mitm import MITM
from .middleware import Middleware
from .config import Config
