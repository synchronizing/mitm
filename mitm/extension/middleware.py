"""
Custom middleware implementations for the MITM proxy.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
from typing import Any, TextIO

from mitm import http
from mitm.models import Connection, Middleware

logger = logging.getLogger("mitm")


class Log(Middleware):
    """
    Logs every event and every chunk of raw data to the ``mitm`` logger, at ``INFO``
    level. Configure `logging` to see the output.
    """

    async def mitm_started(self, host: str, port: int):
        logger.info("MITM server started on %s:%d.", host, port)

    async def client_connected(self, connection: Connection):
        logger.info("Client %s has connected.", connection.client)

    async def server_connected(self, connection: Connection):
        logger.info("Client %s has connected to server %s.", connection.client, connection.server)

    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        destination = connection.server if connection.server else "mitm"
        logger.info("Client %s to %s:\n\n\t%s\n", connection.client, destination, indent(data))
        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        logger.info("Server %s to client %s:\n\n\t%s\n", connection.server, connection.client, indent(data))
        return data

    async def client_disconnected(self, connection: Connection):
        logger.info("Client %s has disconnected.", connection.client)

    async def server_disconnected(self, connection: Connection):
        logger.info("Server %s has disconnected.", connection.server)

    async def connection_error(self, connection: Connection, error: Exception):
        logger.warning("Connection from client %s failed: %s", connection.client, error)


class HTTPLog(Middleware):
    """
    Logs every HTTP request and response that passes through the proxy.

    Each exchange is written once its response completes, or its connection closes, so
    concurrent requests never interleave. By default it is one line per exchange:

    .. code-block:: text

          ┊ GET https://example.com/ → 200 OK (text/html, 1.3 KB, 85 ms)

    Args:
        stream: Text stream to write to. Defaults to `sys.stderr`.
        verbose: Also write headers and bodies.
        json: Write one JSON object per exchange (JSON Lines) instead of text.
        max_body: Maximum bytes of each body to keep, or `None` for no limit.

    Attributes:
        count: Number of exchanges written.
    """

    gutter = "  ┊ "

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        verbose: bool = False,
        json: bool = False,
        max_body: int | None = 4096,
    ):
        self.stream = stream
        self.verbose = verbose
        self.json = json
        self.max_body = max_body
        self.count = 0
        self.sessions: dict[int, http.Session] = {}

    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        session = self.sessions.get(id(connection))
        try:
            if session is None:
                limit = self.max_body if self.verbose or self.json else 0
                if data.startswith(b"CONNECT "):
                    connect = http.parse_head(data.partition(b"\r\n\r\n")[0])
                    session = http.Session("https", authority=connect.target, limit=limit)
                    session.connect = connect
                    self.sessions[id(connection)] = session
                    return data
                session = self.sessions[id(connection)] = http.Session("http", limit=limit)
            session.client(data)
        except ValueError:  # Not HTTP; stop parsing this connection.
            if session:
                session.requests.tunnel = session.responses.tunnel = True
        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        if session := self.sessions.get(id(connection)):
            try:
                self.write(*session.server(data))
            except ValueError:
                session.requests.tunnel = session.responses.tunnel = True
        return data

    async def server_disconnected(self, connection: Connection):
        if session := self.sessions.get(id(connection)):
            self.write(*session.close())

    async def client_disconnected(self, connection: Connection):
        if session := self.sessions.pop(id(connection), None):
            self.write(*session.close())

    async def connection_error(self, connection: Connection, error: Exception):
        session = self.sessions.get(id(connection))
        exchanges = session.close() if session else []
        if not exchanges:
            request = session.connect if session else None
            exchanges = [http.Exchange(request, url=request.target if request else str(connection.client))]
        for exchange in exchanges:
            exchange.error = str(error)
        self.write(*exchanges)

    def write(self, *exchanges: http.Exchange):
        """
        Writes exchanges to the stream.
        """
        if not exchanges:
            return
        stream = self.stream or sys.stderr
        if self.json:
            text = "".join(json.dumps(self.record(exchange), ensure_ascii=False) + "\n" for exchange in exchanges)
        else:
            color = stream.isatty() and not os.environ.get("NO_COLOR")
            gutter = f"\x1b[2m{self.gutter}\x1b[0m" if color else self.gutter
            text = "".join(f"{gutter}{line}".rstrip() + "\n" for e in exchanges for line in self.format(e))
        stream.write(text)
        stream.flush()
        self.count += len(exchanges)

    def format(self, exchange: http.Exchange) -> list[str]:
        """
        Returns the lines of text describing `exchange`.
        """
        request, response = exchange.request, exchange.response
        title = f"{request.method} {exchange.url}" if request else exchange.url
        if exchange.error:
            return [f"{title} ✗ {exchange.error}"]
        if not self.verbose:
            return [f"{title} → {self.summary(exchange)}"]

        assert request is not None
        lines = [f"{title} {request.version}", *(f"{name}: {value}" for name, value in request.headers)]
        lines += ["", *self.body(request), ""] if request.size else [""]
        if response:
            lines += [f"{response.line} ({self.summary(exchange, status=False)})"]
            lines += [f"{name}: {value}" for name, value in response.headers]
            lines += ["", *self.body(response), ""] if response.size else [""]
        else:
            lines += ["(no response)", ""]
        return lines

    def summary(self, exchange: http.Exchange, status: bool = True) -> str:
        """
        Returns a short description of the response, e.g. ``200 OK (text/html, 1.3 KB, 85 ms)``.
        """
        response = exchange.response
        if response is None:
            return "(no response)"
        details = [(response.header("Content-Type") or "").split(";")[0], format_size(response.size)]
        if exchange.ended:
            details.append(f"{(exchange.ended - exchange.started) * 1000:.0f} ms")
        if not response.complete:
            details.append("incomplete")
        text = ", ".join(detail for detail in details if detail)
        return f"{response.status} {response.reason} ({text})" if status else text

    def body(self, message: http.Message) -> list[str]:
        """
        Returns the lines of text displaying the body of `message`.
        """
        text, truncated = self.decode(message)
        if text is None:
            kind = message.header("Content-Encoding") or message.header("Content-Type") or "unknown type"
            return [f"<{format_size(message.size)} binary, {kind}>"]
        return [*text.splitlines(), *([f"… truncated ({format_size(message.size)} received)"] if truncated else [])]

    def decode(self, message: http.Message) -> tuple[str | None, bool]:
        """
        Returns the body of `message` as text (or `None` if binary), and whether it was truncated.
        """
        text = http.decode(message, self.max_body)
        limited = self.max_body is not None and text is not None and len(text.encode()) >= self.max_body
        return text, message.truncated or limited

    def record(self, exchange: http.Exchange) -> dict[str, Any]:
        """
        Returns `exchange` as a JSON-serializable dictionary.
        """
        started = datetime.datetime.fromtimestamp(exchange.started, datetime.UTC)
        request, response = exchange.request, exchange.response
        return {
            "time": started.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "duration_ms": round((exchange.ended - exchange.started) * 1000) if exchange.ended else None,
            "request": request
            and {
                "method": request.method,
                "url": exchange.url,
                "version": request.version,
                **self.content(request),
            },
            "response": response
            and {
                "status": response.status,
                "reason": response.reason,
                "version": response.version,
                **self.content(response),
            },
            "error": exchange.error,
        }

    def content(self, message: http.Message) -> dict[str, Any]:
        text, truncated = self.decode(message)
        return {
            "headers": [list(header) for header in message.headers],
            "body": text,
            "body_size": message.size,
            "truncated": truncated,
        }


def indent(data: bytes) -> str:
    try:
        return "\n\t".join(data.decode("utf-8").rstrip("\r\n").splitlines())
    except UnicodeDecodeError:
        return repr(data)


def format_size(size: int) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1000 or unit == "MB":
            return f"{size} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1000
    return ""  # pragma: no cover
