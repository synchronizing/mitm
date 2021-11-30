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
    Exception raised when the protocol did not work.

    This is the only error that `mitm.MITM` will catch. Throwing this error will
    continue the search for a valid protocol.
    """


class Protocol(ABC):
    """
    An abstract class for a custom protocol implementation.

    The `bytes_needed` is used to determine the minimum number of bytes needed to be
    read from the connection to identify all of the protocols. This is done by getting
    the `max()` of the `bytes_needed` of all the protocols, and reading that many
    bytes from the connection.

    Args:
        bytes_needed: The minimum number of bytes needed to identify the protocol.

    Example:

        Template for a protocol implementation:

        .. code-block:: python

            from mitm import Protocol, Connection

            class MyProtocol(Protocol):
                bytes_needed = 4

                @classmethod
                async def connect(cls: Protocol, connection: Connection, data: bytes) -> bool:
                    # Do something with the data.
    """

    bytes_needed: int

    @abstractclassmethod
    async def connect(cls: "Protocol", connection: Connection, data: bytes) -> bool:
        """
        Attempts to connect to destination server using the given data. Returns `True`
        if the connection was successful, raises `InvalidProtocol` if the connection
        failed.

        Returns:
            Whether the connection was successful.

        Raises:
            InvalidProtocol: If the connection failed.

        Note:
            This methods needs to be implemented by subclasses.
        """
        raise NotImplementedError


class HTTP(Protocol):
    """
    Adds support for HTTP protocol (with TLS support).

    This protocol adds HTTP and HTTPS proxy support to the `mitm`. Note that by
    "HTTPS proxy" we mean a proxy that supports the `CONNECT` statement, and not
    one that instantly performs a TLS handshake on connection with the client (though
    this can be added if needed).

    `bytes_needed` is set to 8192 to ensure we can read the first line of the request.
    The HTTP/1.1 protocol does not define a minimum length for the first line, so we
    use the largest number found in other projects.
    """

    bytes_needed = 8192

    @classmethod
    async def connect(cls: Protocol, connection: Connection, data: bytes) -> bool:
        """
        Connects to the destination server if the data is a valid HTTP request.

        Args:
            connection: The connection to the destination server.
            data: The data received from the client.

        Returns:
            Whether the connection was successful.

        Raises:
            InvalidProtocol: If the connection failed.
        """
        try:
            request = httpq.Request.parse(data)
        except:
            raise InvalidProtocol

        # Deal with 'CONNECT'.
        if request.method == "CONNECT":

            # Get the hostname and port.
            if not request.target:
                raise InvalidProtocol
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
                raise InvalidProtocol

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

            # Get the hostname and port.
            if not "Host" in request.headers:
                raise InvalidProtocol
            host, port = request.headers.get("Host").string, 80

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

        raise InvalidProtocol
