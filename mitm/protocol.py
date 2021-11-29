"""

"""

import asyncio
import ssl
from abc import ABC, abstractclassmethod

import httpq
import toolbox

from .core import Connection, Host


class InvalidProtocol(Exception):
    """
    Protocol did not work.
    """


class Protocol(ABC):
    """
    An abstract class for a custom protocol implementation.

    Attributes:
        bytes_needed: The number of bytes needed to identify the protocol.
    """

    bytes_needed: int

    @abstractclassmethod
    def connect(cls: "Protocol", connection: Connection, data: bytes) -> bool:
        """
        Attempts to connect to destination server using the given message.
        Returns True if successful, returns None otherwise.
        """
        raise NotImplementedError


class HTTP(Protocol):
    """
    Adds man-in-the-middle support for HTTP proxy.
    """

    bytes_needed = 8192

    @classmethod
    async def connect(cls: Protocol, connection: Connection, data: bytes) -> bool:
        try:
            request = httpq.Request.parse(data)
        except:
            return

        # Deal with 'CONNECT'.
        if request.method == "CONNECT":

            if not request.target:
                return
            host, port = request.target.string.split(":")

            # Accept client connection.
            connection.client.writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
            await connection.client.writer.drain()

            # Perform handshake.
            try:
                await toolbox.tls_handshake(
                    reader=connection.client.reader,
                    writer=connection.client.writer,
                    ssl_context=connection.ssl_context,
                    server_side=True,
                )
            except ssl.SSLError:
                return

            # Connect to destination server.
            reader, writer = await asyncio.open_connection(
                host=host,
                port=int(port),
                ssl=True,
            )
            connection.server = Host(reader, writer)

            return True

        # Deal with any other HTTP method.
        elif request.method:

            if not "Host" in request.headers:
                return
            host, port = request.headers.get("Host").string, 80

            print("!", host, port)

            # Connect to destination server and send initial request.
            reader, writer = await asyncio.open_connection(
                host=host,
                port=port,
                ssl=False,
            )
            connection.server = Host(reader, writer)
            connection.server.writer.write(data)
            await connection.server.writer.drain()

            return True

        return False
