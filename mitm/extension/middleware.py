"""
Custom middleware implementations for the MITM proxy.
"""

import datetime
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, TextIO, Tuple

from mitm import http
from mitm.models import Connection, Middleware

logger = logging.getLogger(__package__)


class Log(Middleware):
    """
    Middleware that logs all events to the console.

    Note:
        Events are logged with the `logging` module, at the ``INFO`` level. Make sure
        `logging` is configured to see them (e.g. ``logging.basicConfig(level=logging.INFO)``).
    """

    async def mitm_started(self, host: str, port: int):
        logger.info(f"MITM server started on {host}:{port}.")

    async def client_connected(self, connection: Connection):
        logger.info(f"Client {connection.client} has connected.")

    async def server_connected(self, connection: Connection):
        logger.info(f"Client {connection.client} has connected to server {connection.server}.")

    async def client_data(self, connection: Connection, data: bytes) -> bytes:

        # The first request is intended for the 'mitm' server to discover the
        # destination server.
        if not connection.server:
            logger.info(f"Client {connection.client} to mitm: \n\n\t{indent(data)}\n")

        # All requests thereafter are intended for the destination server.
        else:
            logger.info(f"Client {connection.client} to {connection.server}: \n\n\t{indent(data)}\n")

        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        logger.info(f"Server {connection.server} to client {connection.client}: \n\n\t{indent(data)}\n")
        return data

    async def client_disconnected(self, connection: Connection):
        logger.info(f"Client {connection.client} has disconnected.")

    async def server_disconnected(self, connection: Connection):
        logger.info(f"Server {connection.server} has disconnected.")

    async def connection_error(self, connection: Connection, error: Exception):
        logger.warning(f"Connection with client {connection.client} failed: {error}")


class HTTPLog(Middleware):
    """
    Middleware that logs all HTTP requests and responses.

    Requests are logged once their response is received (or once the connection closes),
    so requests made at the same time are never mixed together. By default, each request
    is logged in one line:

    .. code-block:: text

          ┊ GET https://example.com/ → 200 OK (text/html, 1.3 KB, 85 ms)

    Args:
        stream: The stream to log to. Defaults to `sys.stderr`.
        verbose: Whether to log the headers and bodies too.
        json: Whether to log each request as a JSON object, one per line.
        max_body: Max size of each body that is logged. Use `None` for no limit.
            Defaults to 4096.

    Attributes:
        count: The number of requests that were logged.
    """

    gutter = "  ┊ "

    def __init__(
        self,
        stream: Optional[TextIO] = None,
        verbose: bool = False,
        json: bool = False,
        max_body: Optional[int] = 4096,
    ):
        self.stream = stream
        self.verbose = verbose
        self.json = json
        self.max_body = max_body
        self.count = 0

        # Each connection has its own session, which pairs its requests and responses.
        self.sessions: Dict[int, http.Session] = {}

    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        session = self.sessions.get(id(connection))

        try:
            # The first request starts the session. Bodies are only kept if they are logged.
            if session is None:
                limit = self.max_body if self.verbose or self.json else 0

                # The 'CONNECT' request is intended for the 'mitm', and is not logged. The
                # requests that follow are encrypted, and use its target as their host.
                if data.startswith(b"CONNECT "):
                    connect = http.parse_head(data.partition(b"\r\n\r\n")[0])
                    session = http.Session("https", authority=connect.target, limit=limit)
                    session.connect = connect
                    self.sessions[id(connection)] = session
                    return data

                session = http.Session("http", limit=limit)
                self.sessions[id(connection)] = session

            session.client(data)

        # The data is not HTTP, so the rest of the connection is ignored.
        except ValueError:
            if session:
                session.requests.tunnel = True
                session.responses.tunnel = True

        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        session = self.sessions.get(id(connection))
        if session:
            try:
                self.write(*session.server(data))

            # The data is not HTTP, so the rest of the connection is ignored.
            except ValueError:
                session.requests.tunnel = True
                session.responses.tunnel = True

        return data

    async def server_disconnected(self, connection: Connection):
        session = self.sessions.get(id(connection))
        if session:
            self.write(*session.close())

    async def client_disconnected(self, connection: Connection):
        session = self.sessions.pop(id(connection), None)
        if session:
            self.write(*session.close())

    async def connection_error(self, connection: Connection, error: Exception):
        session = self.sessions.get(id(connection))
        exchanges = session.close() if session else []

        # If the connection failed before any request was made (e.g. the server could not
        # be reached), the error is logged with the 'CONNECT' request instead.
        if not exchanges:
            request = session.connect if session else None
            url = request.target if request else str(connection.client)
            exchanges = [http.Exchange(request, url=url)]

        for exchange in exchanges:
            exchange.error = str(error)

        self.write(*exchanges)

    def write(self, *exchanges: http.Exchange):
        """
        Logs the requests.

        Args:
            exchanges: The requests, and their responses.
        """
        if not exchanges:
            return

        stream = self.stream if self.stream else sys.stderr

        # Logs each request as a JSON object.
        if self.json:
            text = ""
            for exchange in exchanges:
                text += json.dumps(self.record(exchange), ensure_ascii=False) + "\n"

        # Logs each request as text, with a dim gutter if the stream is a terminal.
        else:
            gutter = self.gutter
            if stream.isatty() and not os.environ.get("NO_COLOR"):
                gutter = f"\x1b[2m{self.gutter}\x1b[0m"

            text = ""
            for exchange in exchanges:
                for line in self.format(exchange):
                    text += f"{gutter}{line}".rstrip() + "\n"

        stream.write(text)
        stream.flush()
        self.count += len(exchanges)

    def format(self, exchange: http.Exchange) -> List[str]:
        """
        Formats the request, and its response, as lines of text.

        Args:
            exchange: The request, and its response.
        """
        request, response = exchange.request, exchange.response
        title = f"{request.method} {exchange.url}" if request else exchange.url

        # Failed requests are logged in one line.
        if exchange.error:
            return [f"{title} ✗ {exchange.error}"]

        # By default, requests are logged in one line too.
        if not self.verbose:
            return [f"{title} → {self.summary(exchange)}"]

        # Request with its headers and body.
        lines = [f"{title} {request.version}"]
        for name, value in request.headers:
            lines.append(f"{name}: {value}")
        lines.append("")
        if request.size:
            lines += [*self.body(request), ""]

        # Response with its headers and body.
        if response:
            lines.append(f"{response.line} ({self.summary(exchange, status=False)})")
            for name, value in response.headers:
                lines.append(f"{name}: {value}")
            lines.append("")
            if response.size:
                lines += [*self.body(response), ""]
        else:
            lines += ["(no response)", ""]

        return lines

    def summary(self, exchange: http.Exchange, status: bool = True) -> str:
        """
        Summarizes the response (e.g. ``200 OK (text/html, 1.3 KB, 85 ms)``).

        Args:
            exchange: The request, and its response.
            status: Whether to include the status of the response.
        """
        response = exchange.response
        if response is None:
            return "(no response)"

        details = []
        content_type = response.header("Content-Type")
        if content_type:
            details.append(content_type.split(";")[0])
        details.append(format_size(response.size))
        if exchange.ended:
            details.append(f"{(exchange.ended - exchange.started) * 1000:.0f} ms")
        if not response.complete:
            details.append("incomplete")

        if status:
            return f"{response.status} {response.reason} ({', '.join(details)})"
        return ", ".join(details)

    def body(self, message: http.Message) -> List[str]:
        """
        Formats the body of a message as lines of text.

        Args:
            message: The request or response.
        """
        text, truncated = self.decode(message)

        # Binary bodies are summarized instead.
        if text is None:
            kind = message.header("Content-Encoding") or message.header("Content-Type") or "unknown type"
            return [f"<{format_size(message.size)} binary, {kind}>"]

        lines = text.splitlines()
        if truncated:
            lines.append(f"… truncated ({format_size(message.size)} received)")
        return lines

    def decode(self, message: http.Message) -> Tuple[Optional[str], bool]:
        """
        Decodes the body of a message into text.

        Args:
            message: The request or response.

        Returns:
            A tuple containing the body as text (or `None` if it is binary), and a bool
            that indicates if the body was cut short.
        """
        text = http.decode(message, self.max_body)
        limited = self.max_body is not None and text is not None and len(text.encode()) >= self.max_body
        return text, message.truncated or limited

    def record(self, exchange: http.Exchange) -> Dict[str, Any]:
        """
        Formats the request, and its response, as a JSON object.

        Args:
            exchange: The request, and its response.
        """
        started = datetime.datetime.fromtimestamp(exchange.started, datetime.timezone.utc)
        record = {
            "time": started.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "duration_ms": None,
            "request": None,
            "response": None,
            "error": exchange.error,
        }

        if exchange.ended:
            record["duration_ms"] = round((exchange.ended - exchange.started) * 1000)

        if exchange.request:
            record["request"] = {
                "method": exchange.request.method,
                "url": exchange.url,
                "version": exchange.request.version,
                **self.content(exchange.request),
            }

        if exchange.response:
            record["response"] = {
                "status": exchange.response.status,
                "reason": exchange.response.reason,
                "version": exchange.response.version,
                **self.content(exchange.response),
            }

        return record

    def content(self, message: http.Message) -> Dict[str, Any]:
        """
        Formats the headers and body of a message as a JSON object.

        Args:
            message: The request or response.
        """
        text, truncated = self.decode(message)
        return {
            "headers": [list(header) for header in message.headers],
            "body": text,
            "body_size": message.size,
            "truncated": truncated,
        }


def indent(data: bytes) -> str:
    """
    Indents raw data for logging. Binary data is logged as is.

    Args:
        data: The data to indent.
    """
    try:
        return "\n\t".join(data.decode("utf-8").rstrip("\r\n").splitlines())
    except UnicodeDecodeError:
        return repr(data)


def format_size(size: float) -> str:
    """
    Formats a size in bytes (e.g. ``1.3 KB``).

    Args:
        size: The size in bytes.
    """
    if size < 1000:
        return f"{size} B"
    if size < 1000 * 1000:
        return f"{size / 1000:.1f} KB"
    return f"{size / 1000 / 1000:.1f} MB"
