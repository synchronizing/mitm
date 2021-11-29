__author__ = "Felipe Faria"

import appdirs
import pathlib

__data__ = pathlib.Path(appdirs.user_data_dir(__package__, __author__))

import logging
import sys

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)


from .core import *
from .protocol import *
from .middleware import *
from .mitm import *
