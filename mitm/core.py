"""
Core components of the MITM framework.
"""

import asyncio
import ssl
from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass
class Host:
    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None

    def __bool__(self):
        return self.reader is not None and self.writer is not None


@dataclass
class Connection:
    client: Host
    server: Host
    ssl_context: ssl.SSLContext


class Flow(Enum):
    CLIENT_TO_SERVER = 0
    SERVER_TO_CLIENT = 1
