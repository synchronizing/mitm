"""
Man-in-the-middle.
"""

import asyncio
import contextlib
import pathlib
from typing import Dict, List, Optional

from cryptography.hazmat.primitives import serialization

import mitm
from mitm.crypto import CertificateAuthority
from mitm.extension.middleware import HTTPLog
from mitm.extension.protocol import HTTP
from mitm.models import Connection, Host, InvalidProtocol, Middleware, Protocol

CERT_PAGE = (pathlib.Path(__file__).parent / "cert.html").read_bytes()


class MITM:
    """
    Man-in-the-middle proxy server.

    Example:

        .. code-block:: python

            from mitm import MITM

            mitm = MITM()
            mitm.run()

        .. code-block:: python

            async with MITM() as mitm:
                ...
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8888,
        protocols: Optional[List[Protocol]] = None,
        middlewares: Optional[List[Middleware]] = None,
        certificate_authority: Optional[CertificateAuthority] = None,
    ):
        """
        Initializes the MITM class.

        Args:
            host: Host to listen on. Defaults to `127.0.0.1`.
            port: Port to listen on. Use `0` to listen on any free port. Defaults to `8888`.
            protocols: List of protocols to use. Defaults to `[protocol.HTTP]`.
            middlewares: List of middlewares to use. Defaults to `[middleware.HTTPLog]`.
            certificate_authority: Certificate authority to use. Defaults to the one stored
                in `mitm.__data__`, which is generated the first time it is needed.
        """
        self.host = host
        self.port = port

        # Loads the CA certificate and private key, or generates and stores them.
        if certificate_authority:
            self.certificate_authority = certificate_authority
        else:
            self.certificate_authority = CertificateAuthority.init(path=mitm.__data__)

        # Initialize any middleware that is not already initialized.
        middlewares = middlewares if middlewares else [HTTPLog]
        new_middlewares = []
        for middleware in middlewares:
            if isinstance(middleware, type):
                middleware = middleware()
            new_middlewares.append(middleware)
        self.middlewares = new_middlewares

        # Initialize any protocol that is not already initialized.
        protocols = protocols if protocols else [HTTP]
        new_protocols = []
        for protocol in protocols:
            if isinstance(protocol, type):
                protocol = protocol(
                    certificate_authority=self.certificate_authority,
                    middlewares=self.middlewares,
                )
            new_protocols.append(protocol)
        self.protocols = new_protocols

        self.server: Optional[asyncio.Server] = None

        # Connections that are currently open, by the task handling them.
        self.connections: Dict[asyncio.Task, Connection] = {}

    async def start(self):
        """
        Start the MITM proxy server.

        Notes:
            Begins accepting connections immediately. Use `run` for blocking usage,
            or the class as an async context manager for automatic cleanup. If the
            server was started on port `0`, `port` is updated to the port it listens on.

        Raises:
            OSError: If the server cannot bind to the host and port.
        """
        self.server = await asyncio.start_server(self.accept, host=self.host, port=self.port)
        self.port = self.server.sockets[0].getsockname()[1]

        for middleware in self.middlewares:
            await middleware.mitm_started(host=self.host, port=self.port)

    async def stop(self):
        """
        Stop the MITM proxy server, and closes all of its connections.
        """
        if not self.server:
            return

        # Stops accepting new connections.
        self.server.close()

        # Drops the connections that are still open. Each connection then finishes on its
        # own, calling the middlewares as usual. Connections that do not finish in time are
        # cancelled.
        for connection in self.connections.values():
            for host in (connection.client, connection.server):
                if host.writer:
                    host.writer.transport.abort()

        if self.connections:
            await asyncio.wait(self.connections, timeout=5)

            # Connections remove themselves once they finish, so any left did not.
            pending = list(self.connections)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        await self.server.wait_closed()
        self.server = None

    def run(self):
        """
        Run the MITM proxy server (blocking).

        Notes:
            Starts the server and serves forever until interrupted.
            For non-blocking usage, use `start` and `stop` directly.
        """

        async def serve():
            await self.start()
            try:
                await self.server.serve_forever()
            finally:
                await self.stop()

        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(serve())

    async def __aenter__(self) -> "MITM":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        await self.stop()
        return False

    async def accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        Accepts a new connection from a client.

        Warning:
            This method is not intended to be called directly.
        """
        task = asyncio.current_task()
        connection = Connection(client=Host(reader=reader, writer=writer), server=Host())

        # Keeps track of the connection while it is open, so it can be closed by `stop`.
        self.connections[task] = connection
        try:
            await self.mitm(connection)
        finally:
            del self.connections[task]

    async def mitm(self, connection: Connection):
        """
        Handles an incoming connection (single connection).

        Warning:
            This method is not intended to be called directly.
        """
        try:
            #  Calls middlewares for client initial connect.
            for middleware in self.middlewares:
                await middleware.client_connected(connection=connection)

            # Gets the bytes needed to identify the protocol.
            min_bytes_needed = max(proto.bytes_needed for proto in self.protocols)
            data = await connection.client.reader.read(n=min_bytes_needed)

            # The client closed the connection without sending anything.
            if not data:
                return

            # Direct requests (GET /path, not GET http://...) are intended for the 'mitm'
            # itself, and are served by the certificate page. Note that these must never be
            # proxied, as the 'Host' header would point the 'mitm' back to itself.
            line = data.split(b"\r\n", 1)[0].split(b" ")
            if len(line) == 3 and line[1].startswith(b"/") and line[2].startswith(b"HTTP/"):
                await self.serve_certificate(connection, data)
                return

            # Calls middleware on client's data.
            for middleware in self.middlewares:
                data = await middleware.client_data(connection=connection, data=data)

            # Finds the protocol that matches the data.
            proto = None
            for prtcl in self.protocols:
                proto = prtcl
                try:
                    # Attempts to resolve the protocol, and connect to the server.
                    host, port, tls = await proto.resolve(connection=connection, data=data)
                    await proto.connect(connection=connection, host=host, port=port, tls=tls, data=data)
                except InvalidProtocol:
                    proto = None
                else:
                    # Stop searching for working protocols.
                    break

            # No protocol was found for the data.
            if not proto:
                raise ValueError("No protocol was found. Check the protocols list.")

            # Protocol identified, but we did not connect to a server.
            if not connection.server:
                raise ValueError(
                    "The protocol was found, but the server was not connected to successfully. "
                    f"Check the {proto.__class__.__name__} implementation."
                )

            # Sets the connection protocol.
            connection.protocol = proto

            # Calls middleware for server initial connect.
            for middleware in self.middlewares:
                await middleware.server_connected(connection=connection)

            # Handles the data between the client and server.
            await proto.handle(connection=connection)

        # Calls middleware if the connection failed (e.g. the server could not be reached).
        except Exception as err:
            for middleware in self.middlewares:
                await middleware.connection_error(connection=connection, error=err)

        finally:
            # If a server connection exists after handling it, we close it.
            if connection.server and connection.server.mitm_managed:
                await close(connection.server.writer)

                # Calls the server's 'disconnected' middleware.
                for middleware in self.middlewares:
                    await middleware.server_disconnected(connection=connection)

            # Attempts to disconnect with the client.
            if connection.client and connection.client.mitm_managed:
                await close(connection.client.writer)

                # Calls the client 'disconnected' middleware.
                for middleware in self.middlewares:
                    await middleware.client_disconnected(connection=connection)

    async def serve_certificate(self, connection: Connection, data: bytes):
        """
        Serves the certificate page for direct (non-proxy) requests.

        Note:
            The page is served at ``/``, and the CA certificate is served at ``/cert.pem``
            (PEM format), and at ``/cert.cer`` and ``/cert.crt`` (DER format).

        Args:
            connection: The connection with the client.
            data: The request from the client.
        """
        method, path = data.decode("latin-1").split(" ", 2)[:2]
        status, content_type, body = "200 OK", "text/html; charset=utf-8", CERT_PAGE
        disposition = ""

        # Only 'GET' and 'HEAD' requests are supported.
        if method not in ("GET", "HEAD"):
            status, content_type, body = "405 Method Not Allowed", "text/plain; charset=utf-8", b"Method Not Allowed\n"

        # Serves the CA certificate as a download.
        elif path in ("/cert.pem", "/cert.cer", "/cert.crt"):
            if path == "/cert.pem":
                body = self.certificate_authority.cert.public_bytes(serialization.Encoding.PEM)
                content_type = "application/x-pem-file"
            else:
                body = self.certificate_authority.cert.public_bytes(serialization.Encoding.DER)
                content_type = "application/x-x509-ca-cert"
            extension = path.split(".")[-1]
            disposition = f"Content-Disposition: attachment; filename=mitm-ca.{extension}\r\n"

        # Everything that is not the page itself does not exist.
        elif path != "/":
            status, content_type, body = "404 Not Found", "text/plain; charset=utf-8", b"Not Found\n"

        header = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{disposition}"
            f"Connection: close\r\n"
            f"\r\n"
        )

        # Responses to 'HEAD' requests do not have a body.
        if method == "HEAD":
            body = b""

        connection.client.writer.write(header.encode() + body)
        await connection.client.writer.drain()


async def close(writer: asyncio.StreamWriter):
    """
    Closes the connection with a host.

    Note:
        In some instances 'wait_closed()' might hang. This is a known issue that happens
        when and if the host keeps the connection alive (or never acknowledges that a TLS
        connection was closed), and, unfortunately, there is nothing we can do about it.
        This is a reported bug in asyncio: https://bugs.python.org/issue39758. To avoid
        hanging forever the connection is dropped if it does not close within a second.

    Args:
        writer: The writer of the host.
    """
    writer.close()
    try:
        await asyncio.wait_for(writer.wait_closed(), timeout=1)
    except (OSError, TimeoutError):
        writer.transport.abort()

        # The connection is only dropped in the next iteration of the event loop.
        await asyncio.sleep(0)
