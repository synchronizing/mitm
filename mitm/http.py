"""
HTTP/1.x parsing functionalities.

Used by the `mitm` to find where a request is going, and by the `HTTPLog` middleware to
log every request and response that goes through it.
"""

import codecs
import time
import zlib
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, List, Optional, Tuple

try:
    from compression import zstd
except ImportError:  # pragma: no cover
    # Python 3.13 and below do not support zstd.
    zstd = None

MAX_HEAD = 64 * 1024
"""
Max size of the start line and headers of an HTTP message. Defaults to 64KB.
"""

TEXT_TYPES = ("text/", "json", "xml", "javascript", "x-www-form-urlencoded", "graphql", "event-stream", "yaml")
"""
Content types whose body is decoded as text, even if it contains invalid characters.
"""

BINARY_TYPES = ("image/", "audio/", "video/", "font/", "octet-stream", "zip", "pdf", "protobuf", "grpc", "wasm")
"""
Content types whose body is never decoded as text.
"""


@dataclass
class Message:
    """
    Dataclass representing an HTTP/1.x request or response.

    Args:
        line: The first line of the message (e.g. ``GET / HTTP/1.1``, ``HTTP/1.1 200 OK``).
        headers: The headers of the message, as name and value pairs.
        body: The body of the message, with any chunked encoding removed.
        size: The size of the body that was received.
        complete: Whether or not the whole message was received.

    Note:
        The body might be cut short to save memory (see `Parser`), in which case `size`
        is larger than the body.
    """

    line: str
    headers: List[Tuple[str, str]] = field(default_factory=list)
    body: bytes = b""
    size: int = 0
    complete: bool = False

    @property
    def is_response(self) -> bool:
        """
        Returns whether or not the message is a response.
        """
        return self.line.startswith("HTTP/")

    @property
    def method(self) -> str:
        """
        Returns the method of the request (e.g. ``GET``).
        """
        return self.line.split(" ", 1)[0]

    @property
    def target(self) -> str:
        """
        Returns the target of the request (e.g. ``/``, ``http://example.com/``).
        """
        return self.line.split(" ", 2)[1]

    @property
    def version(self) -> str:
        """
        Returns the HTTP version of the message (e.g. ``HTTP/1.1``).
        """
        parts = self.line.split(" ", 2)
        return parts[0] if self.is_response else parts[-1]

    @property
    def status(self) -> int:
        """
        Returns the status of the response (e.g. ``200``).
        """
        return int(self.line.split(" ", 2)[1])

    @property
    def reason(self) -> str:
        """
        Returns the reason of the response (e.g. ``OK``).
        """
        parts = self.line.split(" ", 2)
        return parts[2] if len(parts) > 2 else ""

    @property
    def truncated(self) -> bool:
        """
        Returns whether or not the body was cut short.
        """
        return self.size > len(self.body)

    def header(self, name: str) -> Optional[str]:
        """
        Returns the first value of the header, or `None` if the header does not exist.

        Args:
            name: The name of the header. Not case sensitive.
        """
        name = name.lower()
        for key, value in self.headers:
            if key.lower() == name:
                return value
        return None


def parse_head(head: bytes) -> Message:
    """
    Parses the first line and headers of an HTTP message.

    Args:
        head: The first line and headers, without the empty line that ends them.

    Raises:
        ValueError: If the data is not an HTTP/1.x request or response.
    """
    line, *lines = head.decode("latin-1").split("\r\n")
    parts = line.split(" ", 2)

    # Checks the first line of the response (e.g. 'HTTP/1.1 200 OK').
    if line.startswith("HTTP/"):
        if len(parts) < 2 or not (parts[1].isdigit() and len(parts[1]) == 3):
            raise ValueError(f"Not an HTTP status line: {line!r}")

    # Checks the first line of the request (e.g. 'GET / HTTP/1.1').
    elif len(parts) != 3 or not parts[2].startswith("HTTP/"):
        raise ValueError(f"Not an HTTP request line: {line!r}")

    # Parses the headers.
    headers = []
    for header in lines:
        name, colon, value = header.partition(":")
        if not colon:
            raise ValueError(f"Malformed header: {header!r}")
        headers.append((name.strip(), value.strip()))

    return Message(line, headers)


def split_authority(authority: str, default_port: int) -> Tuple[str, int]:
    """
    Splits the host and port of an authority (e.g. ``example.com:443``, ``[::1]:443``).

    Args:
        authority: The authority to split.
        default_port: The port to use if the authority does not have one.

    Raises:
        ValueError: If the port is not a number.
    """

    # Deal with IPv6 addresses (e.g. '[::1]:443').
    if authority.startswith("["):
        host, rest = authority[1:].split("]", 1)
        port = rest.removeprefix(":")

    # Deal with hostnames and IPv4 addresses (e.g. 'example.com:443').
    elif authority.count(":") == 1:
        host, port = authority.split(":")

    # Deal with authorities without a port, including IPv6 addresses without brackets.
    else:
        host, port = authority, ""

    return host, int(port) if port else default_port


class Parser:
    """
    Parses a stream of HTTP/1.x data, one chunk at a time, into messages.

    A connection carries two streams: the requests from the client, and the responses
    from the server. Each stream needs its own parser.

    Args:
        response: Whether the stream contains responses. Defaults to requests.
        limit: Max size of the body kept for each message. Defaults to no limit.
        method: Function that returns the method of the request the next response is
            for. Called once per response, as responses to 'HEAD' requests have no body.

    Attributes:
        tunnel: Whether the connection switched protocols (e.g. to WebSockets). Once it
            does, the rest of the stream is not HTTP, and is ignored.
        message: The message being parsed, once its first line and headers are parsed.
    """

    def __init__(
        self,
        response: bool = False,
        limit: Optional[int] = None,
        method: Optional[Callable[[], str]] = None,
    ):
        self.response = response
        self.limit = limit
        self.method = method if method else lambda: "GET"
        self.tunnel = False
        self.message: Optional[Message] = None

        # Data that was received but not parsed yet, and the body of the current message.
        self.buffer = bytearray()
        self.body = bytearray()

        # Size of the body that is left to be read, or `None` if the body ends when the
        # connection closes.
        self.remaining: Optional[int] = None

        # Whether the body is chunked, and the state of the current chunk: `None` when the
        # size of the chunk is next, the size left to read, `0` when the empty line that
        # ends the chunk is next, or `-1` when the trailers are next.
        self.chunked = False
        self.chunk: Optional[int] = None

    def feed(self, data: bytes) -> List[Message]:
        """
        Parses a chunk of data.

        Args:
            data: The data to parse.

        Returns:
            The messages that were completed by the data.

        Raises:
            ValueError: If the data is not valid HTTP/1.x.
        """
        messages: List[Message] = []
        self.buffer += data

        while self.buffer and not self.tunnel:
            # Parses the first line and headers of a new message.
            if self.message is None:
                if not self.read_head(messages):
                    break

            # Parses the body of a chunked message.
            elif self.chunked:
                if not self.read_chunk(messages):
                    break

            # Parses the body of a message that ends when the connection closes.
            elif self.remaining is None:
                self.keep(self.buffer)
                self.buffer.clear()

            # Parses the body of a message with a 'Content-Length'.
            else:
                size = min(self.remaining, len(self.buffer))
                self.keep(self.buffer[:size])
                del self.buffer[:size]
                self.remaining -= size
                if self.remaining == 0:
                    self.finish(messages)

        return messages

    def close(self) -> Optional[Message]:
        """
        Called when the stream closes.

        Note:
            A message whose body ends when the connection closes is complete at this
            point. Any other message is incomplete.

        Returns:
            The message that was being parsed, if any.
        """
        message = self.message
        if message is None or self.tunnel:
            return None

        message.body = bytes(self.body)
        message.complete = self.remaining is None and not self.chunked
        self.message = None
        return message

    def read_head(self, messages: List[Message]) -> bool:
        """
        Parses the first line and headers of a message, and figures out how its body ends.

        Args:
            messages: List the message is added to, if it is complete.

        Returns:
            Whether or not there was enough data to parse.
        """

        # Removes empty lines between messages, which some clients send.
        while self.buffer.startswith(b"\r\n"):
            del self.buffer[:2]

        # Waits for the empty line that ends the headers.
        end = self.buffer.find(b"\r\n\r\n")
        if end < 0:
            if len(self.buffer) > MAX_HEAD:
                raise ValueError("HTTP head is too large")
            return False

        message = parse_head(bytes(self.buffer[:end]))
        if message.is_response != self.response:
            raise ValueError(f"Unexpected first line: {message.line!r}")
        del self.buffer[: end + 4]

        self.message = message
        self.body = bytearray()
        self.chunked, self.chunk = False, None
        self.remaining = 0

        # Deal with responses that do not have a body, or that switch protocols.
        if self.response:
            status = message.status

            # Informational responses (e.g. '100 Continue') are followed by the real one.
            if 100 <= status < 200 and status != 101:
                self.message = None
                return True

            method = self.method()
            if status == 101 or (method == "CONNECT" and 200 <= status < 300):
                self.tunnel = True
                self.finish(messages)
                return True

            if method == "HEAD" or status in (204, 304):
                self.finish(messages)
                return True

        # Figures out where the body ends.
        transfer_encoding = (message.header("Transfer-Encoding") or "").lower()
        content_length = message.header("Content-Length")
        if "chunked" in transfer_encoding:
            self.chunked = True
        elif content_length is not None:
            self.remaining = int(content_length)
        elif self.response:
            self.remaining = None

        # Messages without a body are complete.
        if self.remaining == 0 and not self.chunked:
            self.finish(messages)

        return True

    def read_chunk(self, messages: List[Message]) -> bool:
        """
        Parses the next part of a chunked body.

        Args:
            messages: List the message is added to, if it is complete.

        Returns:
            Whether or not there was enough data to parse.
        """

        # Reads the data of the current chunk.
        if self.chunk is not None and self.chunk > 0:
            size = min(self.chunk, len(self.buffer))
            self.keep(self.buffer[:size])
            del self.buffer[:size]
            self.chunk -= size
            return True

        # Everything else is a line: the size of a chunk, the end of a chunk, or a trailer.
        end = self.buffer.find(b"\r\n")
        if end < 0:
            return False
        line = bytes(self.buffer[:end])
        del self.buffer[: end + 2]

        # Size of the next chunk. A size of zero is the last chunk, followed by trailers.
        if self.chunk is None:
            size = int(line.split(b";", 1)[0].strip(), 16)
            self.chunk = size if size else -1

        # End of the current chunk.
        elif self.chunk == 0:
            self.chunk = None

        # An empty line ends the trailers, and the message.
        elif not line:
            self.finish(messages)

        return True

    def keep(self, data: bytes):
        """
        Adds data to the body of the current message, up to the limit.

        Args:
            data: Part of the body.
        """
        self.message.size += len(data)
        room = len(data) if self.limit is None else self.limit - len(self.body)
        if room > 0:
            self.body += data[:room]

    def finish(self, messages: List[Message]):
        """
        Completes the current message.

        Args:
            messages: List the message is added to.
        """
        self.message.body = bytes(self.body)
        self.message.complete = True
        messages.append(self.message)
        self.message = None


@dataclass
class Exchange:
    """
    Dataclass representing an HTTP request and its response.

    Args:
        request: The request, or `None` if the client did not send a valid one.
        response: The response, or `None` if one was not received.
        url: The full URL of the request (e.g. ``https://example.com/``).
        started: When the request was received.
        ended: When the response was received.
        error: Why the request failed, if it did.
    """

    request: Optional[Message]
    response: Optional[Message] = None
    url: str = ""
    started: float = field(default_factory=time.time)
    ended: Optional[float] = None
    error: Optional[str] = None


class Session:
    """
    Pairs the requests and responses of a connection.

    Args:
        scheme: The scheme of the connection. Either ``http``, or ``https`` for
            connections that were opened with 'CONNECT'.
        authority: The target of the 'CONNECT' request, used for requests that do not
            have a 'Host' header.
        limit: Max size of the body kept for each message. Defaults to no limit.

    Attributes:
        connect: The 'CONNECT' request that opened the connection, if any.
    """

    def __init__(self, scheme: str = "http", authority: Optional[str] = None, limit: Optional[int] = None):
        self.scheme = scheme
        self.authority = authority
        self.connect: Optional[Message] = None

        # Requests that are waiting for a response, and requests whose response is being
        # received.
        self.pending: Deque[Exchange] = deque()
        self.answering: Deque[Exchange] = deque()

        # Parsers for each side of the connection.
        self.requests = Parser(limit=limit)
        self.responses = Parser(response=True, limit=limit, method=self.next_method)

    def client(self, data: bytes):
        """
        Called when data is received from the client.

        Args:
            data: The data received from the client.
        """
        for request in self.requests.feed(data):
            self.pending.append(Exchange(request, url=self.url(request)))

    def server(self, data: bytes) -> List[Exchange]:
        """
        Called when data is received from the server.

        Args:
            data: The data received from the server.

        Returns:
            The requests that received their full response.
        """
        exchanges = []
        for response in self.responses.feed(data):
            exchanges.append(self.pair(response))
        return exchanges

    def close(self) -> List[Exchange]:
        """
        Called when the connection closes.

        Returns:
            Every request that has not been returned yet, with or without a response.
        """
        exchanges = []

        # The response might have been waiting for the connection to close.
        response = self.responses.close()
        if response:
            exchanges.append(self.pair(response))

        # The client might have been in the middle of a request.
        request = self.requests.close()
        if request:
            self.pending.append(Exchange(request, url=self.url(request)))

        exchanges.extend(self.pending)
        self.pending.clear()
        return exchanges

    def url(self, request: Message) -> str:
        """
        Returns the full URL of the request.

        Args:
            request: The request.
        """
        target = request.target

        # 'CONNECT' requests and requests sent to a proxy already have the full URL.
        if request.method == "CONNECT" or "://" in target:
            return target

        # Everything else has the path only, so the host is taken from the headers.
        authority = request.header("Host") or self.authority or ""
        if self.scheme == "https":
            authority = authority.removesuffix(":443")

        return f"{self.scheme}://{authority}{target}"

    def next_method(self) -> str:
        """
        Called by the response parser when a response starts.

        Returns:
            The method of the request the response is for.
        """

        # Responses are sent in the same order as the requests.
        if self.pending:
            exchange = self.pending.popleft()

        # The server might respond before the request is complete (e.g. '413').
        else:
            request = self.requests.message
            exchange = Exchange(request, url=self.url(request) if request else "")

        self.answering.append(exchange)
        return exchange.request.method if exchange.request else "GET"

    def pair(self, response: Message) -> Exchange:
        """
        Pairs a response with its request.

        Args:
            response: The response.
        """
        exchange = self.answering.popleft()
        exchange.response = response
        exchange.ended = time.time()

        # After switching protocols (e.g. to WebSockets) the client stops sending HTTP.
        if response.status == 101:
            self.requests.tunnel = True

        return exchange


def decode(message: Message, limit: Optional[int] = None) -> Optional[str]:
    """
    Decodes the body of a message into text.

    Note:
        Bodies compressed with gzip, deflate, or zstd (Python 3.14+) are decompressed.

    Args:
        message: The message.
        limit: Max size of the body to decode. Defaults to no limit.

    Returns:
        The body as text, or `None` if the body is binary or cannot be decompressed.
    """
    body = message.body
    cut = message.truncated

    # Decompresses the body.
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

    # Cuts the body to the limit.
    if limit is not None:
        cut = cut or len(body) >= limit
        body = body[:limit]

    # Ignores binary bodies.
    content_type = (message.header("Content-Type") or "").lower()
    if any(kind in content_type for kind in BINARY_TYPES) or b"\x00" in body:
        return None

    # Gets the charset of the body, if it is a valid one.
    charset = content_type.partition("charset=")[2].split(";")[0].strip(' "') or "utf-8"
    try:
        codecs.lookup(charset)
    except LookupError:
        charset = "utf-8"

    # Decodes the body. If the body was cut short, the last character might be cut too.
    try:
        return body.decode(charset)
    except UnicodeDecodeError as err:
        if cut and err.start >= len(body) - 3:
            return body[: err.start].decode(charset, errors="replace")

    # Text that contains invalid characters is still text.
    if any(kind in content_type for kind in TEXT_TYPES):
        return body.decode(charset, errors="replace")

    return None


def inflate(body: bytes, encoding: str, limit: Optional[int]) -> bytes:
    """
    Decompresses a gzip or deflate body.

    Args:
        body: The compressed body.
        encoding: Either ``gzip`` or ``deflate``.
        limit: Max size of the decompressed body. Defaults to no limit.
    """
    wbits = zlib.MAX_WBITS | 32 if "gzip" in encoding else zlib.MAX_WBITS
    try:
        return zlib.decompressobj(wbits).decompress(body, limit or 0)
    except zlib.error:
        if encoding != "deflate":
            raise

        # Some servers send 'deflate' without the zlib header.
        return zlib.decompressobj(-zlib.MAX_WBITS).decompress(body, limit or 0)
