import gzip
import zlib

import pytest

from mitm.http import Message, Parser, Session, decode, parse_head, split_authority


def feed(parser, data, size=None):
    """
    Feeds the data to the parser in chunks of the given size.
    """
    size = size if size else len(data)
    messages = []
    for i in range(0, len(data), size):
        messages += parser.feed(data[i : i + size])
    return messages


class Test_parse_head:
    def test_request(self):
        message = parse_head(b"GET /path HTTP/1.1\r\nHost: example.com\r\nX-Time: 12:00")
        assert message.method == "GET"
        assert message.target == "/path"
        assert message.version == "HTTP/1.1"
        assert message.headers == [("Host", "example.com"), ("X-Time", "12:00")]

        # Headers are not case sensitive.
        assert message.header("host") == "example.com"
        assert message.header("missing") is None

    def test_response(self):
        message = parse_head(b"HTTP/1.1 404 Not Found")
        assert message.version == "HTTP/1.1"
        assert message.status == 404
        assert message.reason == "Not Found"

        # The reason is optional.
        assert parse_head(b"HTTP/1.1 204").reason == ""

    @pytest.mark.parametrize("head", [b"junk", b"GET /", b"HTTP/1.1 OK", b"GET / HTTP/1.1\r\nno colon"])
    def test_invalid(self, head):
        with pytest.raises(ValueError):
            parse_head(head)


@pytest.mark.parametrize(
    "authority, expected",
    [
        ("example.com", ("example.com", 443)),
        ("example.com:8443", ("example.com", 8443)),
        ("[::1]", ("::1", 443)),
        ("[::1]:8443", ("::1", 8443)),
        ("::1", ("::1", 443)),
    ],
)
def test_split_authority(authority, expected):
    assert split_authority(authority, 443) == expected


def test_split_authority_invalid():
    with pytest.raises(ValueError):
        split_authority("example.com:https", 443)


class Test_Parser:
    @pytest.mark.parametrize("size", [None, 1, 7])
    def test_content_length(self, size):
        data = b"POST / HTTP/1.1\r\nContent-Length: 5\r\n\r\nhelloGET /next HTTP/1.1\r\n\r\n"
        first, second = feed(Parser(), data, size)
        assert first.body == b"hello"
        assert first.size == 5
        assert first.complete
        assert second.target == "/next"

    @pytest.mark.parametrize("size", [None, 1, 3])
    def test_chunked(self, size):
        data = (
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
            b"5;extension=1\r\nhello\r\n1\r\n!\r\n0\r\nX-Trailer: 1\r\n\r\n"
        )
        [message] = feed(Parser(response=True), data, size)
        assert message.body == b"hello!"

    def test_until_close(self):
        parser = Parser(response=True)
        assert parser.feed(b"HTTP/1.0 200 OK\r\n\r\npart one, ") == []
        assert parser.feed(b"part two") == []

        # The response is complete once the connection closes.
        message = parser.close()
        assert message.body == b"part one, part two"
        assert message.complete

    def test_incomplete(self):
        parser = Parser(response=True)
        parser.feed(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc")

        # The connection closed before the whole body was received.
        message = parser.close()
        assert message.body == b"abc"
        assert not message.complete
        assert parser.close() is None

    @pytest.mark.parametrize("status", [204, 304])
    def test_no_body_status(self, status):
        [message] = Parser(response=True).feed(b"HTTP/1.1 %d X\r\nContent-Length: 10\r\n\r\n" % status)
        assert message.body == b""

    def test_head_response(self):
        parser = Parser(response=True, method=lambda: "HEAD")
        [message] = parser.feed(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n")
        assert message.complete

    def test_informational_response(self):
        data = b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        [message] = Parser(response=True).feed(data)
        assert message.status == 200

    def test_switching_protocols(self):
        parser = Parser(response=True)
        [message] = parser.feed(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n\x81\x05hello")
        assert message.status == 101

        # The rest of the stream is not HTTP.
        assert parser.tunnel
        assert parser.feed(b"more frames") == []

    def test_limit(self):
        [message] = Parser(limit=3).feed(b"POST / HTTP/1.1\r\nContent-Length: 5\r\n\r\nhello")
        assert message.body == b"hel"
        assert message.size == 5
        assert message.truncated

    def test_empty_lines(self):
        [message] = Parser().feed(b"\r\n\r\nGET / HTTP/1.1\r\n\r\n")
        assert message.method == "GET"

    @pytest.mark.parametrize(
        "data",
        [
            b"\x16\x03\x01\x02\x00" + b"\x00" * 70_000,
            b"HTTP/1.1 200 OK\r\n\r\n",
            b"POST / HTTP/1.1\r\nContent-Length: nan\r\n\r\n",
        ],
    )
    def test_invalid(self, data):
        with pytest.raises(ValueError):
            Parser().feed(data)


class Test_Session:
    def test_keep_alive(self):
        session = Session("https", authority="example.com:443")
        session.client(b"HEAD /a HTTP/1.1\r\nHost: example.com\r\n\r\nGET /b HTTP/1.1\r\n\r\n")
        first, second = session.server(
            b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nHTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\nok"
        )

        # The response to the 'HEAD' request does not have a body, even with a 'Content-Length'.
        assert first.url == "https://example.com/a"
        assert first.response.status == 200
        assert first.response.body == b""

        # The request without a 'Host' header uses the target of the 'CONNECT' request.
        assert second.url == "https://example.com/b"
        assert second.response.status == 201
        assert second.response.body == b"ok"
        assert second.ended >= second.started

    def test_url(self):
        session = Session("http")
        assert session.url(parse_head(b"GET http://example.com/x HTTP/1.1")) == "http://example.com/x"
        assert session.url(parse_head(b"GET /x HTTP/1.1\r\nHost: example.com:8080")) == "http://example.com:8080/x"

    def test_close(self):
        session = Session()
        session.client(b"GET http://example.com/ HTTP/1.1\r\n\r\n")
        session.client(b"POST http://example.com/ HTTP/1.1\r\nContent-Length: 9\r\n\r\npart")

        # Every request is returned, even without a response.
        first, second = session.close()
        assert first.response is None
        assert first.request.complete
        assert second.request.body == b"part"
        assert not second.request.complete
        assert session.close() == []

    def test_early_response(self):
        session = Session()
        session.client(b"POST http://example.com/ HTTP/1.1\r\nContent-Length: 999\r\n\r\npart")

        # The server responds before the request is complete.
        [exchange] = session.server(b"HTTP/1.1 413 Too Large\r\nContent-Length: 0\r\n\r\n")
        assert exchange.request.method == "POST"
        assert exchange.response.status == 413

    def test_switching_protocols(self):
        session = Session()
        session.client(b"GET http://example.com/ws HTTP/1.1\r\nUpgrade: websocket\r\n\r\n")
        [exchange] = session.server(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
        assert exchange.response.status == 101

        # The data that follows is ignored.
        session.client(b"\x81\x05hello")
        assert session.close() == []


class Test_decode:
    def message(self, body, *headers, size=None):
        return Message("HTTP/1.1 200 OK", list(headers), body, size if size else len(body), True)

    def test_text(self):
        assert decode(self.message(b"caf\xc3\xa9")) == "café"
        assert decode(self.message(b"caf\xe9", ("Content-Type", "text/plain; charset=latin-1"))) == "café"
        assert decode(self.message(b"hi", ("Content-Type", "text/plain; charset=bogus"))) == "hi"

    def test_binary(self):
        assert decode(self.message(b"\x89PNG", ("Content-Type", "image/png"))) is None
        assert decode(self.message(b"a\x00b")) is None
        assert decode(self.message(b"\xff\xfe\xfd")) is None

        # Text with invalid characters is still text.
        assert decode(self.message(b"\xff", ("Content-Type", "text/plain"))) == "�"

    def test_truncated(self):

        # The body was cut short in the middle of the 'é' character.
        assert decode(self.message(b"caf\xc3", size=10)) == "caf"

    def test_compressed(self):
        assert decode(self.message(gzip.compress(b"zipped"), ("Content-Encoding", "gzip"))) == "zipped"
        assert decode(self.message(zlib.compress(b"deflated"), ("Content-Encoding", "deflate"))) == "deflated"
        assert decode(self.message(gzip.compress(b"x" * 100), ("Content-Encoding", "gzip")), limit=10) == "x" * 10

        # Some servers send 'deflate' without the zlib header.
        compressor = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        body = compressor.compress(b"raw deflate") + compressor.flush()
        assert decode(self.message(body, ("Content-Encoding", "deflate"))) == "raw deflate"

    def test_unsupported_encoding(self):
        assert decode(self.message(b"\x1b\x00", ("Content-Encoding", "br"))) is None
        assert decode(self.message(b"not gzip", ("Content-Encoding", "gzip"))) is None
