"""
Man-in-the-middle.
"""

from __future__ import annotations

import asyncio
import contextlib
import pathlib

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

            MITM().run()  # Blocks until interrupted.

        .. code-block:: python

            async with MITM(port=0) as proxy:  # Port 0 picks a free port.
                print(proxy.port)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8888,
        protocols: list[Protocol | type[Protocol]] | None = None,
        middlewares: list[Middleware | type[Middleware]] | None = None,
        certificate_authority: CertificateAuthority | None = None,
    ):
        """
        Initializes the MITM class.

        Args:
            host: Host to listen on. Defaults to `127.0.0.1`.
            port: Port to listen on, or `0` for any free port. Defaults to `8888`.
            protocols: Protocols to use. Defaults to `[protocol.HTTP]`.
            middlewares: Middlewares to use. Defaults to `[middleware.HTTPLog]`.
            certificate_authority: Certificate authority to use. Defaults to the one stored
                in `mitm.__data__`, which is created on first use.
        """
        self.host = host
        self.port = port
        self.certificate_authority = certificate_authority or CertificateAuthority.init(mitm.__data__)
        self.middlewares = [m() if isinstance(m, type) else m for m in middlewares or [HTTPLog]]
        self.protocols = [
            p(certificate_authority=self.certificate_authority, middlewares=self.middlewares)
            if isinstance(p, type)
            else p
            for p in protocols or [HTTP]
        ]
        self.server: asyncio.Server | None = None
        self.connections: dict[asyncio.Task, Connection] = {}

    async def start(self):
        """
        Start the MITM proxy server, and begin accepting connections.

        Notes:
            Use `run` for blocking usage, or the class as an async context manager for
            automatic cleanup. When `port` is `0`, it is updated to the port bound.

        Raises:
            OSError: If the server cannot bind to the host and port.
        """
        self.server = await asyncio.start_server(self.accept, host=self.host, port=self.port)
        self.port = self.server.sockets[0].getsockname()[1]

        for middleware in self.middlewares:
            await middleware.mitm_started(host=self.host, port=self.port)

    async def stop(self):
        """
        Stop the MITM proxy server, and close every open connection.
        """
        if self.server:
            self.server.close()

            # Dropping the sockets lets each connection unwind (and call its middlewares) on
            # its own; only connections still busy after a few seconds are cancelled.
            for connection in self.connections.values():
                for host in (connection.client, connection.server):
                    if host.writer:
                        host.writer.transport.abort()
            if self.connections:
                pending = (await asyncio.wait(self.connections, timeout=5))[1]
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

            await self.server.wait_closed()
            self.server = None

    def run(self):
        """
        Run the MITM proxy server until interrupted (blocking).
        """

        async def serve():
            await self.start()
            try:
                await self.server.serve_forever()
            finally:
                await self.stop()

        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(serve())

    async def __aenter__(self) -> MITM:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        task = asyncio.current_task()
        connection = self.connections[task] = Connection(client=Host(reader=reader, writer=writer), server=Host())
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
            for middleware in self.middlewares:
                await middleware.client_connected(connection=connection)

            # Gets the bytes needed to identify the protocol.
            data = await connection.client.reader.read(n=max(proto.bytes_needed for proto in self.protocols))
            if not data:
                return

            # Requests addressed to the proxy itself (`GET /`, not `GET http://...`) get the certificate page.
            if data.startswith(b"GET /"):
                await self.serve_certificate(connection, data)
                return

            for middleware in self.middlewares:
                data = await middleware.client_data(connection=connection, data=data)

            # Finds the first protocol that can resolve the data, and connects to the server.
            for proto in self.protocols:
                try:
                    host, port, tls = await proto.resolve(connection=connection, data=data)
                    await proto.connect(connection=connection, host=host, port=port, tls=tls, data=data)
                except InvalidProtocol:
                    continue
                break
            else:
                raise InvalidProtocol(f"no protocol matched the client's data: {data[:50]!r}")

            if not connection.server:
                raise ConnectionError(f"{proto!r} did not connect to a server")
            connection.protocol = proto

            for middleware in self.middlewares:
                await middleware.server_connected(connection=connection)

            await proto.handle(connection=connection)

        except Exception as err:
            for middleware in self.middlewares:
                await middleware.connection_error(connection=connection, error=err)

        finally:
            if connection.server and connection.server.mitm_managed:
                await close(connection.server.writer)
                for middleware in self.middlewares:
                    await middleware.server_disconnected(connection=connection)

            if connection.client and connection.client.mitm_managed:
                await close(connection.client.writer)
                for middleware in self.middlewares:
                    await middleware.client_disconnected(connection=connection)

    async def serve_certificate(self, connection: Connection, data: bytes):
        """
        Serves the certificate download page, and the CA certificate in PEM and DER format.
        """
        path = data.split(b" ", 2)[1].decode("latin-1")
        cert = self.certificate_authority.cert
        status, content_type, body = "200 OK", "text/html; charset=utf-8", CERT_PAGE
        headers = ""

        if path in ("/cert.pem", "/cert.cer", "/cert.crt"):
            encoding = serialization.Encoding.PEM if path == "/cert.pem" else serialization.Encoding.DER
            body = cert.public_bytes(encoding)
            content_type = "application/x-pem-file" if path == "/cert.pem" else "application/x-x509-ca-cert"
            headers = f"Content-Disposition: attachment; filename=mitm-ca{path[5:]}\r\n"
        elif path != "/":
            status, content_type, body = "404 Not Found", "text/plain; charset=utf-8", b"Not Found\n"

        head = (
            f"HTTP/1.1 {status}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"{headers}"
            f"Connection: close\r\n\r\n"
        )
        connection.client.writer.write(head.encode() + body)
        await connection.client.writer.drain()


async def close(writer: asyncio.StreamWriter):
    # A TLS close waits for the peer's acknowledgment, which may never come: give up after a second.
    writer.close()
    try:
        await asyncio.wait_for(writer.wait_closed(), timeout=1)
    except (OSError, TimeoutError):
        writer.transport.abort()
        await asyncio.sleep(0)  # The socket is released on the next loop iteration.
