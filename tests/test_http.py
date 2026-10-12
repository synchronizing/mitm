import gzip
import zlib

import pytest

from mitm.http import Message, Parser, Session, decode, parse_head, split_authority


def feed(parser: Parser, data: bytes, step: int | None = None) -> list[Message]:
    step = step or len(data)
    return [message for i in range(0, len(data), step) for message in parser.feed(data[i : i + step])]


class TestParseHead:
    def test_request(self):
        message = parse_head(b"GET /path HTTP/1.1\r\nHost: example.com\r\nX-A: 1:2")
        assert (message.method, message.target, message.version) == ("GET", "/path", "HTTP/1.1")
        assert message.headers == [("Host", "example.com"), ("X-A", "1:2")]
        assert message.header("host") == "example.com"
        assert message.header("missing") is None

    def test_response(self):
        message = parse_head(b"HTTP/1.1 404 Not Found")
        assert (message.version, message.status, message.reason) == ("HTTP/1.1", 404, "Not Found")
        assert parse_head(b"HTTP/1.1 204").reason == ""

    @pytest.mark.parametrize("head", [b"junk", b"GET /", b"HTTP/1.1 OK", b"GET / HTTP/1.1\r\nno colon"])
    def test_invalid(self, head):
        with pytest.raises(ValueError):
            parse_head(head)


@pytest.mark.parametrize(
    ("authority", "expected"),
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


def test_split_authority_invalid_port():
    with pytest.raises(ValueError):
        split_authority("example.com:https", 443)


class TestParser:
    @pytest.mark.parametrize("step", [None, 1, 7])
    def test_content_length(self, step):
        data = b"POST / HTTP/1.1\r\nContent-Length: 5\r\n\r\nhelloGET /next HTTP/1.1\r\n\r\n"
        first, second = feed(Parser(), data, step)
        assert (first.body, first.size, first.complete) == (b"hello", 5, True)
        assert second.target == "/next"

    @pytest.mark.parametrize("step", [None, 1, 3])
    def test_chunked(self, step):
        head = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n"
        data = head + b"5;ext=1\r\nhello\r\n1\r\n!\r\n0\r\nX-Trailer: 1\r\n\r\n"
        [message] = feed(Parser(response=True), data, step)
        assert message.body == b"hello!"

    def test_until_close(self):
        parser = Parser(response=True)
        assert parser.feed(b"HTTP/1.0 200 OK\r\n\r\npart one, ") == []
        assert parser.feed(b"part two") == []
        message = parser.close()
        assert (message.body, message.complete) == (b"part one, part two", True)

    def test_incomplete(self):
        parser = Parser(response=True)
        parser.feed(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\nabc")
        message = parser.close()
        assert (message.body, message.complete) == (b"abc", False)
        assert parser.close() is None

    @pytest.mark.parametrize("status", [204, 304])
    def test_no_body_status(self, status):
        [message] = Parser(response=True).feed(b"HTTP/1.1 %d X\r\nContent-Length: 10\r\n\r\n" % status)
        assert message.body == b""

    def test_head_response(self):
        parser = Parser(response=True, method=lambda: "HEAD")
        [message] = parser.feed(b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n")
        assert message.complete

    def test_interim_response(self):
        [message] = Parser(response=True).feed(
            b"HTTP/1.1 100 Continue\r\n\r\nHTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        )
        assert message.status == 200

    def test_upgrade(self):
        parser = Parser(response=True)
        [message] = parser.feed(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n\x81\x05hello")
        assert message.status == 101
        assert parser.tunnel
        assert parser.feed(b"more frames") == []

    def test_limit(self):
        [message] = Parser(limit=3).feed(b"POST / HTTP/1.1\r\nContent-Length: 5\r\n\r\nhello")
        assert (message.body, message.size, message.truncated) == (b"hel", 5, True)

    def test_stray_crlf(self):
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


class TestSession:
    def test_pairs_keep_alive(self):
        session = Session("https", authority="example.com:443")
        session.client(b"HEAD /a HTTP/1.1\r\nHost: example.com\r\n\r\nGET /b HTTP/1.1\r\n\r\n")
        first, second = session.server(
            b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\nHTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\nok"
        )
        assert (first.url, first.response.status, first.response.body) == ("https://example.com/a", 200, b"")
        assert (second.url, second.response.status, second.response.body) == ("https://example.com/b", 201, b"ok")
        assert second.ended >= second.started

    def test_url(self):
        session = Session("http")
        assert session.url(parse_head(b"GET http://example.com/x HTTP/1.1")) == "http://example.com/x"
        assert session.url(parse_head(b"GET /x HTTP/1.1\r\nHost: example.com:8080")) == "http://example.com:8080/x"

    def test_close_flushes_unanswered(self):
        session = Session()
        session.client(b"GET http://example.com/ HTTP/1.1\r\n\r\n")
        session.client(b"POST http://example.com/ HTTP/1.1\r\nContent-Length: 9\r\n\r\npart")
        first, second = session.close()
        assert first.response is None and first.request.complete
        assert second.request.body == b"part" and not second.request.complete
        assert session.close() == []

    def test_early_response(self):
        session = Session()
        session.client(b"POST http://example.com/ HTTP/1.1\r\nContent-Length: 999\r\n\r\npart")
        [exchange] = session.server(b"HTTP/1.1 413 Too Large\r\nContent-Length: 0\r\n\r\n")
        assert (exchange.request.method, exchange.response.status) == ("POST", 413)

    def test_upgrade_stops_parsing(self):
        session = Session()
        session.client(b"GET http://example.com/ws HTTP/1.1\r\nUpgrade: websocket\r\n\r\n")
        [exchange] = session.server(b"HTTP/1.1 101 Switching Protocols\r\n\r\n")
        session.client(b"\x81\x05hello")
        assert exchange.response.status == 101
        assert session.close() == []


class TestDecode:
    def message(self, body, *headers, size=None):
        return Message("HTTP/1.1 200 OK", list(headers), body, len(body) if size is None else size, True)

    def test_text(self):
        assert decode(self.message(b"caf\xc3\xa9")) == "café"
        assert decode(self.message(b"caf\xe9", ("Content-Type", "text/plain; charset=latin-1"))) == "café"
        assert decode(self.message(b"hi", ("Content-Type", "text/plain; charset=bogus"))) == "hi"

    def test_binary(self):
        assert decode(self.message(b"\x89PNG", ("Content-Type", "image/png"))) is None
        assert decode(self.message(b"a\x00b")) is None
        assert decode(self.message(b"\xff\xfe\xfd")) is None
        assert decode(self.message(b"\xff", ("Content-Type", "text/plain"))) == "�"

    def test_truncated_multibyte(self):
        assert decode(self.message(b"caf\xc3", size=10)) == "caf"

    def test_compressed(self):
        assert decode(self.message(gzip.compress(b"zipped"), ("Content-Encoding", "gzip"))) == "zipped"
        assert decode(self.message(zlib.compress(b"deflated"), ("Content-Encoding", "deflate"))) == "deflated"
        raw = zlib.compressobj(wbits=-zlib.MAX_WBITS)
        body = raw.compress(b"raw deflate") + raw.flush()
        assert decode(self.message(body, ("Content-Encoding", "deflate"))) == "raw deflate"
        assert decode(self.message(gzip.compress(b"x" * 100), ("Content-Encoding", "gzip")), limit=10) == "x" * 10

    def test_unsupported_encoding(self):
        assert decode(self.message(b"\x1b\x00", ("Content-Encoding", "br"))) is None
        assert decode(self.message(b"not gzip", ("Content-Encoding", "gzip"))) is None
