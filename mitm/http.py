"""
Minimal HTTP/1.x parsing, used to route proxy requests and to log exchanges.
"""

from __future__ import annotations

import codecs
import time
import zlib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

try:
    from compression import zstd  # Python 3.14+.
except ImportError:  # pragma: no cover
    zstd = None

MAX_HEAD = 64 * 1024

TEXT_TYPES = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded", "graphql", "event-stream", "yaml")
BINARY_TYPES = ("image/", "audio/", "video/", "font/", "octet-stream", "zip", "pdf", "protobuf", "grpc", "wasm")


@dataclass
class Message:
    """
    An HTTP/1.x request or response.

    Attributes:
        line: The start line, e.g. ``GET / HTTP/1.1`` or ``HTTP/1.1 200 OK``.
        headers: Header name and value pairs, in the order received.
        body: The body, after removing chunked encoding. May be cut short; see `size`.
        size: Number of body bytes received, which exceeds ``len(body)`` when truncated.
        complete: Whether the whole message was received.
    """

    line: str
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""
    size: int = 0
    complete: bool = False

    @property
    def is_response(self) -> bool:
        return self.line.startswith("HTTP/")

    @property
    def method(self) -> str:
        return self.line.split(" ", 1)[0]

    @property
    def target(self) -> str:
        return self.line.split(" ", 2)[1]

    @property
    def version(self) -> str:
        parts = self.line.split(" ", 2)
        return parts[0] if self.is_response else parts[-1]

    @property
    def status(self) -> int:
        return int(self.line.split(" ", 2)[1])

    @property
    def reason(self) -> str:
        parts = self.line.split(" ", 2)
        return parts[2] if len(parts) > 2 else ""

    @property
    def truncated(self) -> bool:
        return self.size > len(self.body)

    def header(self, name: str) -> str | None:
        """
        Returns the first value of header `name` (case-insensitive), or `None`.
        """
        name = name.lower()
        return next((value for key, value in self.headers if key.lower() == name), None)


def parse_head(head: bytes) -> Message:
    """
    Parses a start line and headers, without the terminating blank line.

    Raises:
        ValueError: If `head` is not an HTTP/1.x request or response head.
    """
    line, *lines = head.decode("latin-1").split("\r\n")
    parts = line.split(" ", 2)
    if line.startswith("HTTP/"):
        if len(parts) < 2 or not (parts[1].isdigit() and len(parts[1]) == 3):
            raise ValueError(f"Not an HTTP status line: {line!r}")
    elif len(parts) != 3 or not parts[2].startswith("HTTP/"):
        raise ValueError(f"Not an HTTP request line: {line!r}")

    headers = []
    for raw in lines:
        name, sep, value = raw.partition(":")
        if not sep:
            raise ValueError(f"Malformed header: {raw!r}")
        headers.append((name.strip(), value.strip()))
    return Message(line, headers)


def split_authority(authority: str, default_port: int) -> tuple[str, int]:
    """
    Splits ``host``, ``host:port``, ``[v6]`` or ``[v6]:port`` into host and port.

    Raises:
        ValueError: If the port is not a number.
    """
    if authority.startswith("["):
        host, _, rest = authority[1:].partition("]")
        port = rest.removeprefix(":")
    elif authority.count(":") == 1:
        host, port = authority.split(":")
    else:
        host, port = authority, ""
    return host, int(port) if port else default_port


class Parser:
    """
    Incrementally splits one direction of an HTTP/1.x byte stream into messages.

    Args:
        response: Whether the stream carries responses rather than requests.
        limit: Maximum body bytes kept per message, or `None` to keep everything.
        method: Called once per final response head, returning the method of the
            request it answers, which decides whether it has a body (e.g. ``HEAD``).
    """

    def __init__(self, response: bool = False, limit: int | None = None, method: Callable[[], str] | None = None):
        self.response = response
        self.limit = limit
        self.method = method or (lambda: "GET")
        self.tunnel = False  # Set after a protocol switch; the rest of the stream is opaque.
        self.message: Message | None = None  # Message whose body is being read.
        self.buffer = bytearray()
        self.body = bytearray()
        self.remaining: int | None = None  # Body bytes left, or `None` to read until close.
        self.chunk: int | None = None  # Chunked state: `None` size line, >0 data, 0 CRLF, -1 trailers.
        self.chunked = False

    def feed(self, data: bytes) -> list[Message]:
        """
        Consumes `data` and returns the messages it completed.

        Raises:
            ValueError: If the stream is not valid HTTP/1.x.
        """
        done: list[Message] = []
        self.buffer += data
        while self.buffer and not self.tunnel:
            if self.message is None:
                if not self.read_head(done):
                    break
            elif self.chunked:
                if not self.read_chunk(done):
                    break
            elif self.remaining is None:
                self.keep(self.buffer)
                self.buffer.clear()
            else:
                take = min(self.remaining, len(self.buffer))
                self.keep(self.buffer[:take])
                del self.buffer[:take]
                self.remaining -= take
                if self.remaining == 0:
                    self.finish(done)
        return done

    def close(self) -> Message | None:
        """
        Signals the end of the stream and returns the message in progress, if any.
        A body delimited by the connection closing is complete; anything else is not.
        """
        message = self.message
        if message is None or self.tunnel:
            return None
        message.body, message.complete = bytes(self.body), self.remaining is None and not self.chunked
        self.message = None
        return message

    def read_head(self, done: list[Message]) -> bool:
        while self.buffer.startswith(b"\r\n"):  # Tolerate stray CRLFs between messages.
            del self.buffer[:2]
        end = self.buffer.find(b"\r\n\r\n")
        if end < 0:
            if len(self.buffer) > MAX_HEAD:
                raise ValueError("HTTP head too large")
            return False

        message = parse_head(bytes(self.buffer[:end]))
        if message.is_response != self.response:
            raise ValueError(f"Unexpected start line: {message.line!r}")
        del self.buffer[: end + 4]
        self.message, self.body, self.chunk = message, bytearray(), None
        self.chunked, self.remaining = False, 0

        transfer_encoding = (message.header("Transfer-Encoding") or "").lower()
        content_length = message.header("Content-Length")
        if self.response:
            status = message.status
            if 100 <= status < 200 and status != 101:
                self.message = None  # Interim response (e.g. `100 Continue`); the real one follows.
                return True
            method = self.method()
            if status == 101 or (method == "CONNECT" and 200 <= status < 300):
                self.tunnel = True
                self.finish(done)
                return True
            if method == "HEAD" or status in (204, 304):
                self.finish(done)
                return True

        if "chunked" in transfer_encoding:
            self.chunked = True
        elif content_length is not None:
            self.remaining = int(content_length)
        elif self.response:
            self.remaining = None

        if self.remaining == 0 and not self.chunked:
            self.finish(done)
        return True

    def read_chunk(self, done: list[Message]) -> bool:
        if self.chunk is not None and self.chunk > 0:
            take = min(self.chunk, len(self.buffer))
            self.keep(self.buffer[:take])
            del self.buffer[:take]
            self.chunk -= take
            return True

        end = self.buffer.find(b"\r\n")
        if end < 0:
            return False
        line = bytes(self.buffer[:end])
        del self.buffer[: end + 2]

        if self.chunk is None:
            size = int(line.split(b";", 1)[0].strip(), 16)
            self.chunk = size if size else -1
        elif self.chunk == 0:
            self.chunk = None
        elif not line:  # Blank line ends the trailers.
            self.finish(done)
        return True

    def keep(self, data: bytes | bytearray):
        assert self.message is not None
        self.message.size += len(data)
        room = len(data) if self.limit is None else self.limit - len(self.body)
        if room > 0:
            self.body += data[:room]

    def finish(self, done: list[Message]):
        assert self.message is not None
        self.message.body, self.message.complete = bytes(self.body), True
        done.append(self.message)
        self.message = None


@dataclass
class Exchange:
    """
    A request and the response it received.

    Attributes:
        request: The request, or `None` if the client sent nothing parseable.
        response: The response, or `None` if none was received.
        url: Absolute URL of the request (authority only, for ``CONNECT``).
        started: When the request was received, as a UNIX timestamp.
        ended: When the response was received, as a UNIX timestamp.
        error: Why the exchange failed, if it did.
    """

    request: Message | None
    response: Message | None = None
    url: str = ""
    started: float = field(default_factory=time.time)
    ended: float | None = None
    error: str | None = None


class Session:
    """
    Pairs the requests and responses of one proxied connection into exchanges.

    Args:
        scheme: ``http``, or ``https`` for connections tunneled through ``CONNECT``.
        authority: The ``CONNECT`` target, used when a request has no ``Host`` header.
        limit: Maximum body bytes kept per message, or `None` to keep everything.

    Attributes:
        connect: The ``CONNECT`` request that opened the tunnel, if any.
    """

    def __init__(self, scheme: str = "http", authority: str | None = None, limit: int | None = None):
        self.scheme = scheme
        self.authority = authority
        self.connect: Message | None = None
        self.pending: deque[Exchange] = deque()  # Requests awaiting a response.
        self.answering: deque[Exchange] = deque()  # Requests whose response is being read.
        self.requests = Parser(limit=limit)
        self.responses = Parser(response=True, limit=limit, method=self.next_method)

    def client(self, data: bytes):
        """
        Consumes data sent by the client.
        """
        for request in self.requests.feed(data):
            self.pending.append(Exchange(request, url=self.url(request)))

    def server(self, data: bytes) -> list[Exchange]:
        """
        Consumes data sent by the server and returns the exchanges it completed.
        """
        return [self.pair(response) for response in self.responses.feed(data)]

    def close(self) -> list[Exchange]:
        """
        Ends the session and returns every exchange still open, finished or not.
        """
        done = []
        if response := self.responses.close():
            done.append(self.pair(response))
        if request := self.requests.close():
            self.pending.append(Exchange(request, url=self.url(request)))
        done.extend(self.pending)
        self.pending.clear()
        return done

    def url(self, request: Message) -> str:
        """
        Returns the absolute URL of `request`.
        """
        target = request.target
        if request.method == "CONNECT" or "://" in target:
            return target
        authority = request.header("Host") or self.authority or ""
        if self.scheme == "https":
            authority = authority.removesuffix(":443")
        return f"{self.scheme}://{authority}{target}"

    def next_method(self) -> str:
        """
        Moves the oldest pending request to `answering` as a response starts, and
        returns its method.
        """
        if self.pending:
            exchange = self.pending.popleft()
        else:  # Server answered before the request finished (e.g. `413`).
            request = self.requests.message
            exchange = Exchange(request, url=self.url(request) if request else "")
        self.answering.append(exchange)
        return exchange.request.method if exchange.request else "GET"

    def pair(self, response: Message) -> Exchange:
        exchange = self.answering.popleft()
        exchange.response, exchange.ended = response, time.time()
        if response.status == 101:
            self.requests.tunnel = True
        return exchange


def decode(message: Message, limit: int | None = None) -> str | None:
    """
    Returns the body of `message` as text, decompressed, or `None` if it is binary or
    uses an unsupported content encoding.

    Args:
        message: The message to decode.
        limit: Maximum number of (decompressed) bytes to decode.
    """
    body, cut = message.body, message.truncated
    encoding = (message.header("Content-Encoding") or "identity").lower()
    try:
        if encoding in ("gzip", "x-gzip", "deflate"):
            body = inflate(body, encoding, limit)
        elif encoding == "zstd" and zstd:
            body = zstd.ZstdDecompressor().decompress(body, max_length=limit or -1)
        elif encoding != "identity":
            return None
    except (zlib.error, ValueError, getattr(zstd, "ZstdError", ValueError)):
        return None
    if limit is not None:
        cut, body = cut or len(body) >= limit, body[:limit]

    content_type = (message.header("Content-Type") or "").lower()
    if any(kind in content_type for kind in BINARY_TYPES) or b"\x00" in body:
        return None
    charset = content_type.partition("charset=")[2].split(";")[0].strip(' "') or "utf-8"
    try:
        codecs.lookup(charset)
    except LookupError:
        charset = "utf-8"

    try:
        return body.decode(charset)
    except UnicodeDecodeError as err:
        if cut and err.start >= len(body) - 3:  # Truncation split a multi-byte character.
            return body[: err.start].decode(charset, errors="replace")
    if any(kind in content_type for kind in TEXT_TYPES):
        return body.decode(charset, errors="replace")
    return None


def inflate(body: bytes, encoding: str, limit: int | None) -> bytes:
    wbits = zlib.MAX_WBITS | 32 if "gzip" in encoding else zlib.MAX_WBITS
    try:
        return zlib.decompressobj(wbits).decompress(body, limit or 0)
    except zlib.error:
        if encoding != "deflate":
            raise
        return zlib.decompressobj(-zlib.MAX_WBITS).decompress(body, limit or 0)  # Raw deflate, sent by some servers.
