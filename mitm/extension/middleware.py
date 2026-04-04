"""
Custom middlware implementation for the MITM proxy.
"""

import logging
import sys

from mitm.models import Connection, Middleware
from mitm.utils import http

DIM = "\x1b[2m"
BOLD = "\x1b[1m"
RESET = "\x1b[0m"
GUTTER = f"{DIM}  ┊{RESET} "

logger = logging.getLogger(__package__)


def format_bytes(data: bytes) -> str:
    """
    Format raw bytes for human-readable logging.

    Notes:
        Attempts UTF-8 decode with line-by-line indentation. Falls back to
        repr for binary data.
    """
    try:
        text = data.decode("utf-8", errors="strict").rstrip("\r\n")
        lines = text.splitlines()
        return "\n\t".join(lines)
    except UnicodeDecodeError:
        return repr(data)


def format_gutter(data: bytes) -> str:
    """
    Format raw bytes with gutter prefix for CLI output.

    Notes:
        Each line is prefixed with a dim `┊` gutter character. Falls back
        to repr for binary data.
    """
    try:
        text = data.decode("utf-8", errors="strict").rstrip("\r\n")
        lines = text.splitlines()
        return "\n".join(f"{GUTTER}{line}" for line in lines)
    except UnicodeDecodeError:
        return f"{GUTTER}{data!r}"


class Log(Middleware):
    """
    Middleware that logs all events to the console.
    """

    def __init__(self):
        self.connection: Connection = None

    async def mitm_started(self, host: str, port: int):
        logger.info(f"MITM server started on {BOLD}{host}:{port}{RESET}.")

    async def client_connected(self, connection: Connection):
        logger.info(f"Client {BOLD}{connection.client}{RESET} has connected.")

    async def server_connected(self, connection: Connection):
        logger.info(
            f"Client {BOLD}{connection.client}{RESET} has connected to server {BOLD}{connection.server}{RESET}."
        )

    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        formatted = format_bytes(data)

        if not connection.server:
            logger.info(f"Client {connection.client} to mitm: \n\n\t{formatted}\n")
        else:  # pragma: no cover
            logger.info(f"Client {connection.client} to {connection.server}: \n\n\t{formatted}\n")

        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        formatted = format_bytes(data)
        logger.info(f"Server {connection.server} to client {connection.client}: \n\n\t{formatted}\n")
        return data

    async def client_disconnected(self, connection: Connection):
        logger.info(f"Client {connection.client} has disconnected.")

    async def server_disconnected(self, connection: Connection):
        logger.info(f"Server {connection.server} has disconnected.")


class CLILog(Middleware):
    """
    Middleware for CLI output with gutter-prefixed traffic display.
    """

    async def mitm_started(self, host: str, port: int):
        sys.stderr.write(f"{DIM}  ┊ proxy listening on {host}:{port}{RESET}\n{GUTTER}\n")

    async def client_connected(self, connection: Connection):
        pass

    async def server_connected(self, connection: Connection):
        sys.stderr.write(f"{GUTTER}{DIM}→ {connection.server}{RESET}\n")

    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        sys.stderr.write(f"{format_gutter(data)}\n{GUTTER}\n")
        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        sys.stderr.write(f"{format_gutter(data)}\n{GUTTER}\n")
        return data

    async def client_disconnected(self, connection: Connection):
        pass

    async def server_disconnected(self, connection: Connection):
        pass


class HTTPLog(Log):  # pragma: no cover
    """
    Middlewares that logs all HTTP events to the console with pretty-print.

    Notes:
        Do not use this middleware if there is a chance that the request or response
        will not be HTTP. This should only be used if you have control of all the
        requests coming into the proxy. If you are setting your computer's proxy
        settings to `mitm` you should not use this middleware as things will not work.
    """

    def __init__(self):  # pylint: disable=super-init-not-called
        self.connection: Connection = None

    async def client_data(self, connection: Connection, data: bytes) -> bytes:

        req = http.Request.parse(data)

        # The first request is intended for the 'mitm' server to discover the
        # destination server.
        if not connection.server:
            logger.info(f"Client {connection.client} to mitm: \n\n{req}\n")

        # All requests thereafter are intended for the destination server.
        else:
            logger.info(f"Client {connection.client} to {connection.server}: \n\n{req}\n")

        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        resp = http.Response.parse(data)
        logger.info(f"Server {connection.server} to client {connection.client}: \n\n{resp}\n")
        return data

    async def client_disconnected(self, connection: Connection):
        logger.info(f"Client {connection.client} has disconnected.")

    async def server_disconnected(self, connection: Connection):
        logger.info(f"Server {connection.server} has disconnected.")
