"""
Custom protocol implementations for the MITM proxy.
"""
import asyncio
import ssl
from typing import Tuple

from httpq import Request
from toolbox.asyncio.streams import tls_handshake

from mitm.core import Connection, Flow, Host, InvalidProtocol, Protocol


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

    bytes_needed: int = 8192
    buffer_size: int = 8192
    timeout: int = 15
    keep_alive: bool = True

    async def resolve(self, connection: Connection, data: bytes) -> Tuple[str, int, bool]:
        """
        Resolves the destination server for the protocol.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Returns:
            A tuple containing the host, port, and bool if the connection is encrypted.

        Raises:
            InvalidProtocol: If the connection failed.
        """
        try:
            request = Request.parse(data)
        except:  # pragma: no cover
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
            if "Host" not in request.headers:
                raise InvalidProtocol
            host, port = request.headers.get("Host").string, 80

        # Unable to parse the request.
        elif not request.method:
            raise InvalidProtocol

        return host, int(port), tls

    async def connect(self, connection: Connection, host: str, port: int, tls: bool, data: bytes):
        """
        Connects to the destination server if the data is a valid HTTP request.

        Args:
            connection: The connection to the destination server.
            host: The hostname of the destination server.
            port: The port of the destination server.
            tls: Whether the connection is encrypted.
            data: The initial data received from the client.

        Raises:
            InvalidProtocol: If the connection failed.
        """

        # Generate certificate if TLS.
        if tls:

            # Accept client connection.
            connection.client.writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
            await connection.client.writer.drain()

            # Generates new context specific to the host.
            ssl_context = self.certificate_authority.new_context(host)

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

        Args:
            connection: Client/server connection to relay.
            event: Event to wait on.
            flow: The flow to relay.
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
