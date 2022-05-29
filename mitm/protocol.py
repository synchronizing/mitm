"""
Custom protocol implementations for the MITM proxy.
"""
import asyncio
import ssl
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from httpq import Request
from toolbox.asyncio.streams import tls_handshake

from .core import Connection, Flow, Host
from .crypto import CertificateAuthority, new_ssl_context
from .middleware import Middleware


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

    def __init__(
        self,
        bytes_needed: int = 8192,
        buffer_size: int = 8192,
        timeout: int = 5,
        keep_alive: bool = True,
        ca: CertificateAuthority = CertificateAuthority(),
        middlewares: List[Middleware] = [],
    ):
        self.bytes_needed = bytes_needed
        self.buffer_size = buffer_size
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.ca = ca
        self.middlewares = middlewares

    @abstractmethod
    async def resolve(self, connection: Connection, data: bytes) -> Optional[Tuple[str, int, bool]]:
        """
        Resolves the destination of the connection.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Returns:
            A tuple containing the host, port, and bool if the connection is encrypted.

        Raises:
            InvalidProtocol: If the connection failed.

        Note:
            This methods needs to be implemented by subclasses.
        """
        raise NotImplementedError

    @abstractmethod
    async def connect(self, connection: Connection, host: str, port: int, tls: bool, data: bytes):
        """
        Attempts to connect to destination server using the given data. Returns `True`
        if the connection was successful, raises `InvalidProtocol` if the connection
        failed.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Returns:
            Whether the connection was successful.

        Raises:
            InvalidProtocol: If the connection failed.

        Note:
            This methods needs to be implemented by subclasses.
        """
        raise NotImplementedError

    @abstractmethod
    async def handle(self, connection: Connection):
        """
        Handles the connection between a client and a server.

        Args:
            connection: Client/server connection to relay.

        Note:
            This methods needs to be implemented by subclasses.
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<Protocol: {self.__class__.__name__}>"


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

    async def resolve(self, connection: Connection, data: bytes) -> Tuple[str, int, bool]:
        """
        Resolves the destination server for the protocol.
        """
        try:
            request = Request.parse(data)
        except:
            raise InvalidProtocol

        # Deal with 'CONNECT'.
        tls = False
        if request.method == "CONNECT":
            tls = True

            # Get the hostname and port.
            if not request.target:
                raise InvalidProtocol
            host, port = request.target.string.split(":")

        # Deal with any other HTTP method.
        elif request.method:

            # Get the hostname and port.
            if not "Host" in request.headers:
                raise InvalidProtocol
            host, port = request.headers.get("Host").string, 80

        return host, int(port), tls

    async def connect(self, connection: Connection, host: str, port: int, tls: bool, data: bytes):
        """
        Connects to the destination server if the data is a valid HTTP request.

        Args:
            connection: The connection to the destination server.
            data: The initial data received from the client.

        Returns:
            Whether the connection was successful.

        Raises:
            InvalidProtocol: If the connection failed.
        """

        # Generate certificate if TLS.
        if tls:

            # Accept client connection.
            connection.client.writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
            await connection.client.writer.drain()

            # Creates a copy of the destination server X509 certificate.
            cert, key = self.ca.new_X509(host)
            ssl_context = new_ssl_context(cert, key)

            # Perform handshake.
            try:
                await tls_handshake(
                    reader=connection.client.reader,
                    writer=connection.client.writer,
                    ssl_context=ssl_context,
                    server_side=True,
                )
            except ssl.SSLError as err:
                raise InvalidProtocol from err

        # Connect to the destination server and send the initial request.
        reader, writer = await asyncio.open_connection(
            host=host,
            port=port,
            ssl=tls,
        )
        connection.server = Host(reader, writer)

        # Send initial request if not SSL/TLS connection.
        if not tls:
            connection.server.writer.write(data)
            await connection.server.writer.drain()

    async def handle(self, connection: Connection):
        """
        Handles the connection between a client and a server.

        Args:
            connection: Client/server connection to relay.
        """

        # Keeps the connection alive until the client or server closes it.
        run_once = True
        while (
            not connection.client.reader.at_eof()
            and not connection.server.reader.at_eof()
            and (self.keep_alive or run_once)
        ):

            # Keeps trying to relay data until the connection closes.
            event = asyncio.Event()
            await asyncio.gather(
                self.relay(connection, event, Flow.SERVER_TO_CLIENT),
                self.relay(connection, event, Flow.CLIENT_TO_SERVER),
            )

            # Run the while loop only one iteration if keep_alive is False.
            run_once = False

    async def relay(self, connection: Connection, event: asyncio.Event, flow: Flow):
        """
        Relays HTTP data between the client and the server.
        """

        if flow == Flow.CLIENT_TO_SERVER:
            reader = connection.client.reader
            writer = connection.server.writer
        elif flow == Flow.SERVER_TO_CLIENT:
            reader = connection.server.reader
            writer = connection.client.writer

        while not event.is_set() and not reader.at_eof():
            data = None
            try:
                data = await asyncio.wait_for(
                    reader.read(self.buffer_size),
                    timeout=self.timeout,
                )
            except asyncio.exceptions.TimeoutError:
                pass

            if not data:
                event.set()
                break
            else:

                # Pass data through middlewares.
                for mw in self.middlewares:
                    if flow == Flow.SERVER_TO_CLIENT:
                        data = await mw.server_data(connection, data)
                    elif flow == Flow.CLIENT_TO_SERVER:
                        data = await mw.client_data(connection, data)

                writer.write(data)
                await writer.drain()
