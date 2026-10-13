import errno

import pytest

from mitm import HTTP, Connection, Host, InvalidProtocol
from mitm.extension.protocol import describe, origin_form


class Test_HTTP:
    def test_init(self, ca):
        http = HTTP(ca)
        assert http.bytes_needed
        assert http.buffer_size
        assert http.timeout

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "data, expected",
        [
            (b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n", ("example.com", 443, True)),
            (b"CONNECT [::1]:8443 HTTP/1.1\r\n\r\n", ("::1", 8443, True)),
            (b"GET http://example.com/path HTTP/1.1\r\nHost: example.com\r\n\r\n", ("example.com", 80, False)),
            (b"GET http://example.com:8080/ HTTP/1.1\r\n\r\n", ("example.com", 8080, False)),
            # Request that was not received in full.
            (b"GET http://example.com/ HTTP/1.1\r\nHost: exa", ("example.com", 80, False)),
        ],
    )
    async def test_resolve(self, ca, data, expected):
        connection = Connection(Host(), Host())
        assert await HTTP(ca).resolve(connection, data) == expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "data",
        [
            b"junk data",
            b"\x16\x03\x01\x00",
            b"GET /path HTTP/1.1\r\n\r\n",
            b"POST /path HTTP/1.1\r\nHost: example.com:8080\r\n\r\n",
            b"GET https://example.com/ HTTP/1.1\r\n\r\n",
            b"CONNECT example.com:https HTTP/1.1\r\n\r\n",
            b"HTTP/1.1 200 OK\r\n\r\n",
        ],
    )
    async def test_resolve_invalid(self, ca, data):
        connection = Connection(Host(), Host())
        with pytest.raises(InvalidProtocol):
            await HTTP(ca).resolve(connection, data)


@pytest.mark.parametrize(
    "data, expected",
    [
        (
            b"GET http://example.com/a?b=1 HTTP/1.1\r\nHost: example.com\r\nProxy-Connection: keep-alive\r\n\r\nbody",
            b"GET /a?b=1 HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\nbody",
        ),
        (
            b"GET http://example.com HTTP/1.0\r\nConnection: keep-alive\r\nKeep-Alive: 5\r\n\r\n",
            b"GET / HTTP/1.0\r\nConnection: close\r\n\r\n",
        ),
        (
            b"POST /x HTTP/1.1\r\nHost: example.com\r\n\r\n",
            b"POST /x HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n",
        ),
        # Headers that were not received in full are left as is.
        (
            b"GET http://example.com/ HTTP/1.1\r\nHost: exa",
            b"GET / HTTP/1.1\r\nHost: exa",
        ),
    ],
)
def test_origin_form(data, expected):
    assert origin_form(data) == expected


def test_describe():
    assert describe(TimeoutError()) == "timed out"
    assert describe(ConnectionRefusedError(errno.ECONNREFUSED, "Connect call failed")) == "connection refused"
    assert describe(OSError("Multiple exceptions")) == "Multiple exceptions"
