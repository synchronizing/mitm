"""
Custom protocol implementations for the MITM proxy.
"""

import asyncio
import os
import socket
import ssl
import urllib.parse
from typing import List, Optional, Tuple

from mitm import http
from mitm.crypto import CertificateAuthority
from mitm.models import Connection, Flow, Host, InvalidProtocol, Middleware, Protocol


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

    Note:
        Plain HTTP connections carry one request each. The `mitm` asks the server to
        close the connection after the first response, since only the first request
        is rewritten from the proxy format (``GET http://example.com/``) to the format
        servers expect (``GET /``).

    Attributes:
        ssl_context: The SSL context used to connect to, and verify, the destination
            servers. Defaults to `ssl.create_default_context()`.
    """

    bytes_needed: int = 8192
    buffer_size: int = 8192
    timeout: int = 15

    def __init__(
        self,
        certificate_authority: Optional[CertificateAuthority] = None,
        middlewares: Optional[List[Middleware]] = None,
    ):
        """
        Initializes the HTTP protocol.

        Args:
            certificate_authority: The certificate authority to use for the connection.
            middlewares: The middlewares to use for the connection.
        """
        super().__init__(certificate_authority=certificate_authority, middlewares=middlewares)
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.set_alpn_protocols(["http/1.1"])

    async def resolve(self, connection: Connection, data: bytes) -> Tuple[str, int, bool]:
        """
        Resolves the destination server for the protocol.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Returns:
            A tuple containing the host, port, and bool if the connection is encrypted.

        Raises:
            InvalidProtocol: If the data is not an HTTP proxy request.
        """

        # Only parses complete lines, in case the request was not received in full.
        if b"\r\n\r\n" in data:
            head = data.split(b"\r\n\r\n", 1)[0]
        else:
            head = data.rpartition(b"\r\n")[0] or data

        try:
            request = http.parse_head(head)
            if request.is_response:
                raise ValueError("Expected a request, but received a response.")

            # Deal with 'CONNECT'.
            if request.method == "CONNECT":
                host, port = http.split_authority(request.target, 443)

            # Deal with any other HTTP method, which must have the full URL.
            else:
                url = urllib.parse.urlsplit(request.target)
                if url.scheme != "http":
                    raise ValueError(f"Not a proxy request: {request.line!r}")
                host, port = url.hostname, url.port or 80

        # Unable to parse the request.
        except ValueError as err:
            raise InvalidProtocol(str(err)) from err

        if not host:
            raise InvalidProtocol("The request does not have a destination.")

        return host, port, request.method == "CONNECT"

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
            ConnectionError: If the server cannot be reached, or if the TLS handshake with
                the client fails.
        """

        # Connect to the destination server. This happens before the client connection is
        # accepted, so the client can be told if the server cannot be reached.
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host=host, port=port, ssl=self.ssl_context if tls else None),
                timeout=self.timeout,
            )
        except OSError as err:
            message = f"Unable to connect to {host}:{port} ({describe(err)})."
            await self.reply(connection, 502, message)
            raise ConnectionError(message) from err
        connection.server = Host(reader, writer)

        # Send initial request if not SSL/TLS connection.
        if not tls:
            connection.server.writer.write(origin_form(data))
            await connection.server.writer.drain()
            return

        # Accept client connection.
        connection.client.writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await connection.client.writer.drain()

        # Generates new context specific to the host.
        ssl_context = self.certificate_authority.new_context(host)

        # Perform handshake.
        try:
            await connection.client.writer.start_tls(ssl_context, ssl_handshake_timeout=self.timeout)
        except OSError as err:
            raise ConnectionError(
                f"Unable to perform the TLS handshake with the client ({describe(err)}). "
                "The client likely does not trust the mitm certificate authority."
            ) from err

    async def handle(self, connection: Connection):
        """
        Handles the connection between a client and a server.

        Args:
            connection: Client/server connection to relay.
        """

        # Relays data in both directions until either the client or the server closes the
        # connection, at which point the other direction is stopped as well.
        relays = [
            asyncio.create_task(self.relay(connection, Flow.SERVER_TO_CLIENT)),
            asyncio.create_task(self.relay(connection, Flow.CLIENT_TO_SERVER)),
        ]
        try:
            await asyncio.wait(relays, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for relay in relays:
                relay.cancel()
            await asyncio.gather(*relays, return_exceptions=True)

    async def relay(self, connection: Connection, flow: Flow):
        """
        Relays HTTP data between the client and the server.

        Args:
            connection: Client/server connection to relay.
            flow: The flow to relay.
        """

        if flow == Flow.CLIENT_TO_SERVER:
            reader = connection.client.reader
            writer = connection.server.writer
        elif flow == Flow.SERVER_TO_CLIENT:
            reader = connection.server.reader
            writer = connection.client.writer

        try:
            while not reader.at_eof():
                data = await reader.read(self.buffer_size)
                if not data:
                    break

                # Pass data through middlewares.
                for middleware in self.middlewares:
                    if flow == Flow.SERVER_TO_CLIENT:
                        data = await middleware.server_data(connection, data)
                    elif flow == Flow.CLIENT_TO_SERVER:
                        data = await middleware.client_data(connection, data)

                writer.write(data)
                await writer.drain()

        # A connection that is reset, or a TLS connection that is closed abruptly, is
        # treated the same as a connection that was closed normally.
        except OSError:
            pass

    async def reply(self, connection: Connection, status: int, message: str):
        """
        Sends a plain text response to the client.

        Used to tell the client why its request failed (e.g. '502 Bad Gateway' when the
        server cannot be reached).

        Args:
            connection: The connection to reply to.
            status: The status of the response.
            message: The body of the response.
        """
        reasons = {502: "Bad Gateway"}
        body = message.encode() + b"\n"
        head = (
            f"HTTP/1.1 {status} {reasons.get(status, '')}\r\n"
            f"Content-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )

        # The client might have disconnected already.
        try:
            connection.client.writer.write(head.encode() + body)
            await connection.client.writer.drain()
        except OSError:
            pass


def origin_form(data: bytes) -> bytes:
    """
    Rewrites a request sent to a proxy (``GET http://example.com/path``) into the format
    servers expect (``GET /path``).

    Note:
        The request also asks the server to close the connection after responding, as
        any request that follows on the same connection is not rewritten.

    Args:
        data: The initial data received from the client.
    """
    head, separator, body = data.partition(b"\r\n\r\n")
    line, *headers = head.split(b"\r\n")

    # Removes the scheme and host from the target.
    method, target, version = line.split(b" ", 2)
    url = urllib.parse.urlsplit(target)
    if url.scheme:
        target = url.path if url.path else b"/"
        if url.query:
            target += b"?" + url.query

    # Replaces the headers that control the connection, if all of the headers were received.
    if separator:
        hop_by_hop = (b"connection:", b"proxy-connection:", b"keep-alive:")
        headers = [header for header in headers if not header.lower().startswith(hop_by_hop)]
        headers.append(b"Connection: close")

    return b"\r\n".join([b" ".join([method, target, version]), *headers]) + separator + body


def describe(error: OSError) -> str:
    """
    Returns a short description of why a connection failed.

    Args:
        error: The error raised by the connection.
    """
    if isinstance(error, TimeoutError):
        return "timed out"
    if isinstance(error, ssl.SSLCertVerificationError):
        return f"certificate verify failed: {error.verify_message}"
    if isinstance(error, ssl.SSLError) and error.reason:
        return error.reason.replace("_", " ").lower()
    if isinstance(error, socket.gaierror):
        return error.strerror if error.strerror else str(error)
    if error.errno:
        return os.strerror(error.errno).lower()
    return str(error) if str(error) else type(error).__name__
