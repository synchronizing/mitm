"""
Custom protocol implementations for the MITM proxy.
"""

import asyncio
import os
import socket
import ssl
import urllib.parse

from mitm import http
from mitm.crypto import CertificateAuthority
from mitm.models import Connection, Flow, Host, InvalidProtocol, Middleware, Protocol


class HTTP(Protocol):
    """
    Adds support for HTTP protocol (with TLS support).

    Plain HTTP requests (``GET http://...``) are forwarded to the server as-is.
    ``CONNECT`` requests are intercepted: the `mitm` connects to the server, then
    completes the TLS handshake with the client using a certificate signed by its
    certificate authority, so both directions can be read in plain text.

    Attributes:
        ssl_context: Context used to connect to, and verify, TLS servers. Defaults to
            the system's trust store.
    """

    bytes_needed: int = 8192
    buffer_size: int = 8192
    timeout: int = 15

    def __init__(
        self,
        certificate_authority: CertificateAuthority | None = None,
        middlewares: list[Middleware] | None = None,
    ):
        super().__init__(certificate_authority=certificate_authority, middlewares=middlewares)
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.set_alpn_protocols(["http/1.1"])

    async def resolve(self, connection: Connection, data: bytes) -> tuple[str, int, bool]:
        """
        Resolves the destination server from the client's first request.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Returns:
            A tuple containing the host, port, and bool if the connection is encrypted.

        Raises:
            InvalidProtocol: If the data is not an HTTP proxy request.
        """
        head, sep, _ = data.partition(b"\r\n\r\n")
        if not sep:  # Only parse complete lines.
            head = head.rpartition(b"\r\n")[0] or head

        try:
            request = http.parse_head(head)
            if request.is_response:
                raise ValueError("Expected a request")

            if request.method == "CONNECT":
                host, port = http.split_authority(request.target, 443)
            elif "://" in request.target:
                url = urllib.parse.urlsplit(request.target)
                if url.scheme != "http":
                    raise ValueError(f"Unsupported scheme: {url.scheme}")
                host, port = url.hostname, url.port or 80
            else:
                host, port = http.split_authority(request.header("Host") or "", 80)
        except ValueError as err:
            raise InvalidProtocol(str(err)) from err

        if not host:
            raise InvalidProtocol("Request has no destination")
        return host, port, request.method == "CONNECT"

    async def connect(self, connection: Connection, host: str, port: int, tls: bool, data: bytes):
        """
        Connects to the destination server, then either forwards the client's request
        (HTTP) or accepts the tunnel and decrypts it (HTTPS).

        Args:
            connection: Connection object containing a client host.
            host: The hostname of the destination server.
            port: The port of the destination server.
            tls: Whether the connection is encrypted.
            data: The initial data received from the client.

        Raises:
            ConnectionError: If the server is unreachable, or the TLS handshake with the
                client failed.
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, ssl=self.ssl_context if tls else None),
                timeout=self.timeout,
            )
        except OSError as err:
            reason = describe(err)
            await self.reply(connection, 502, f"mitm cannot connect to {host}:{port}: {reason}")
            raise ConnectionError(f"cannot connect to {host}:{port}: {reason}") from err
        connection.server = Host(reader, writer)

        if not tls:
            writer.write(origin_form(data))
            await writer.drain()
            return

        connection.client.writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await connection.client.writer.drain()
        try:
            await connection.client.writer.start_tls(
                self.certificate_authority.new_context(host),
                ssl_handshake_timeout=self.timeout,
            )
        except OSError as err:
            raise ConnectionError(
                f"TLS handshake with the client failed ({describe(err)}); "
                "the client likely does not trust the mitm CA certificate"
            ) from err

    async def handle(self, connection: Connection):
        """
        Relays data between the client and the server until either disconnects.

        Args:
            connection: Client/server connection to relay.
        """
        relays = [asyncio.create_task(self.relay(connection, flow)) for flow in Flow]
        try:
            await asyncio.wait(relays, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for relay in relays:
                relay.cancel()
            await asyncio.gather(*relays, return_exceptions=True)

    async def relay(self, connection: Connection, flow: Flow):
        """
        Relays data in one direction, through the middlewares, until the reader closes.

        Args:
            connection: Client/server connection to relay.
            flow: The direction to relay.
        """
        if flow is Flow.CLIENT_TO_SERVER:
            reader, writer = connection.client.reader, connection.server.writer
        else:
            reader, writer = connection.server.reader, connection.client.writer

        try:
            while data := await reader.read(self.buffer_size):
                for middleware in self.middlewares:
                    if flow is Flow.CLIENT_TO_SERVER:
                        data = await middleware.client_data(connection, data)
                    else:
                        data = await middleware.server_data(connection, data)
                writer.write(data)
                await writer.drain()
        except OSError:  # Resets and abrupt TLS closes end the stream like EOF does.
            pass

    async def reply(self, connection: Connection, status: int, message: str):
        """
        Sends a plain-text response to the client, e.g. ``502`` when the server is unreachable.
        """
        reasons = {502: "Bad Gateway"}
        body = message.encode() + b"\n"
        head = (
            f"HTTP/1.1 {status} {reasons.get(status, '')}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        try:
            connection.client.writer.write(head.encode() + body)
            await connection.client.writer.drain()
        except OSError:
            pass


def origin_form(data: bytes) -> bytes:
    """
    Rewrites a proxy request (``GET http://host/path``) into the form servers expect
    (``GET /path``), and asks the server to close the connection after responding, as
    later requests on it are relayed without being rewritten.
    """
    head, sep, rest = data.partition(b"\r\n\r\n")
    line, *headers = head.split(b"\r\n")
    method, target, version = line.split(b" ", 2)
    url = urllib.parse.urlsplit(target)
    if url.scheme:
        target = (url.path or b"/") + (b"?" + url.query if url.query else b"")

    if sep:
        hop_by_hop = (b"connection:", b"proxy-connection:", b"keep-alive:")
        headers = [header for header in headers if not header.lower().startswith(hop_by_hop)]
        headers.append(b"Connection: close")
    return b"\r\n".join([b" ".join([method, target, version]), *headers]) + sep + rest


def describe(error: OSError) -> str:
    """
    Returns a short, human-readable reason for a connection error.
    """
    if isinstance(error, TimeoutError):
        return "timed out"
    if isinstance(error, ssl.SSLCertVerificationError):
        return f"certificate verify failed: {error.verify_message}"
    if isinstance(error, ssl.SSLError) and error.reason:
        return error.reason.replace("_", " ").lower()
    if isinstance(error, socket.gaierror):
        return error.strerror or str(error)
    if error.errno:
        return os.strerror(error.errno).lower()
    return str(error) or type(error).__name__
