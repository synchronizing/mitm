import io
import json
import logging

import pytest

from mitm import Connection, Host, HTTPLog, Log, Middleware
from mitm.extension.middleware import format_size
from mitm.http import Exchange, parse_head

RESPONSE = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n\r\n{"ok": true}'


def exchange(request, response=None):
    """
    Creates a request, and its response, as if they took 250 ms.
    """
    head, body = request.split(b"\r\n\r\n", 1)
    req = parse_head(head)
    req.body, req.size, req.complete = body, len(body), True
    exchange = Exchange(req, url="https://example.com" + req.target, started=1_700_000_000.0)

    if response:
        head, body = response.split(b"\r\n\r\n", 1)
        exchange.response = parse_head(head)
        exchange.response.body, exchange.response.size, exchange.response.complete = body, len(body), True
        exchange.ended = exchange.started + 0.25

    return exchange


class Test_Middleware:
    connection = Connection(Host(), Host())

    @pytest.mark.asyncio
    async def test_hooks(self):
        middleware = Middleware()
        assert repr(middleware) == "Middleware(Middleware)"

        # Hooks that are not implemented do nothing, and return the data untouched.
        assert await middleware.client_data(self.connection, b"data") == b"data"
        assert await middleware.server_data(self.connection, b"data") == b"data"
        assert await middleware.client_connected(self.connection) is None
        assert await middleware.server_connected(self.connection) is None
        assert await middleware.client_disconnected(self.connection) is None
        assert await middleware.server_disconnected(self.connection) is None
        assert await middleware.connection_error(self.connection, OSError()) is None


class Test_Log:
    log = Log()
    connection = Connection(Host(), Host())

    @pytest.mark.asyncio
    async def test_init(self):
        assert repr(Log()) == "Middleware(Log)"

    @pytest.mark.asyncio
    async def test_events(self, caplog):
        with caplog.at_level(logging.INFO, logger="mitm"):
            await self.log.mitm_started("127.0.0.1", 8888)
            await self.log.client_connected(self.connection)
            await self.log.server_connected(self.connection)
            await self.log.server_disconnected(self.connection)
            await self.log.client_disconnected(self.connection)
            await self.log.connection_error(self.connection, OSError("boom"))

        assert "MITM server started on 127.0.0.1:8888." in caplog.text
        assert "Client <empty host> has connected." in caplog.text
        assert "boom" in caplog.text

    @pytest.mark.asyncio
    async def test_data(self, caplog):
        with caplog.at_level(logging.INFO, logger="mitm"):
            assert await self.log.client_data(self.connection, b"line one\r\nline two") == b"line one\r\nline two"
            assert await self.log.server_data(self.connection, b"\xff") == b"\xff"

        # Text is indented, and binary data is logged as is.
        assert "line one\n\tline two" in caplog.text
        assert "b'\\xff'" in caplog.text


class Test_HTTPLog:
    def write(self, *exchanges, **kwargs):
        """
        Logs the requests, and returns what was logged.
        """
        log = HTTPLog(io.StringIO(), **kwargs)
        log.write(*exchanges)
        assert log.count == len(exchanges)
        return log.stream.getvalue()

    def test_summary(self):
        output = self.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", RESPONSE))
        assert output == "  ┊ GET https://example.com/a → 200 OK (application/json, 12 B, 250 ms)\n"

    def test_summary_no_response(self):
        output = self.write(exchange(b"GET /a HTTP/1.1\r\n\r\n"))
        assert output == "  ┊ GET https://example.com/a → (no response)\n"

    def test_error(self):
        failed = exchange(b"GET /a HTTP/1.1\r\n\r\n")
        failed.error = "Unable to connect."
        assert self.write(failed) == "  ┊ GET https://example.com/a ✗ Unable to connect.\n"

    def test_verbose(self):
        output = self.write(exchange(b"POST /a HTTP/1.1\r\nHost: example.com\r\n\r\nsent", RESPONSE), verbose=True)
        assert output == (
            "  ┊ POST https://example.com/a HTTP/1.1\n"
            "  ┊ Host: example.com\n"
            "  ┊\n"
            "  ┊ sent\n"
            "  ┊\n"
            "  ┊ HTTP/1.1 200 OK (application/json, 12 B, 250 ms)\n"
            "  ┊ Content-Type: application/json; charset=utf-8\n"
            "  ┊\n"
            '  ┊ {"ok": true}\n'
            "  ┊\n"
        )

    def test_verbose_binary(self):
        response = b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\n\r\n\x89PNG"
        output = self.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", response), verbose=True)
        assert "  ┊ <4 B binary, image/png>\n" in output

    def test_verbose_truncated(self):
        output = self.write(exchange(b"POST /a HTTP/1.1\r\n\r\n" + b"x" * 10), verbose=True, max_body=4)
        assert "  ┊ xxxx\n  ┊ … truncated (10 B received)\n" in output
        assert "(no response)" in output

    def test_json(self):
        output = self.write(exchange(b"GET /a HTTP/1.1\r\nAccept: */*\r\n\r\n", RESPONSE), json=True)
        assert json.loads(output) == {
            "time": "2023-11-14T22:13:20.000Z",
            "duration_ms": 250,
            "request": {
                "method": "GET",
                "url": "https://example.com/a",
                "version": "HTTP/1.1",
                "headers": [["Accept", "*/*"]],
                "body": "",
                "body_size": 0,
                "truncated": False,
            },
            "response": {
                "status": 200,
                "reason": "OK",
                "version": "HTTP/1.1",
                "headers": [["Content-Type", "application/json; charset=utf-8"]],
                "body": '{"ok": true}',
                "body_size": 12,
                "truncated": False,
            },
            "error": None,
        }

    def test_color(self, monkeypatch):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        # The gutter is dim on terminals.
        log = HTTPLog(Terminal())
        log.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", RESPONSE))
        assert log.stream.getvalue().startswith("\x1b[2m")

        # Unless colors are disabled.
        monkeypatch.setenv("NO_COLOR", "1")
        log = HTTPLog(Terminal())
        log.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", RESPONSE))
        assert log.stream.getvalue().startswith("  ┊")

    @pytest.mark.asyncio
    async def test_not_http(self):
        log = HTTPLog(io.StringIO())
        connection = Connection(Host(), Host())

        # Data that is not HTTP is ignored, and passed through untouched.
        assert await log.client_data(connection, b"\x16\x03\x01 tls\r\n\r\n") == b"\x16\x03\x01 tls\r\n\r\n"
        assert await log.server_data(connection, b"more") == b"more"
        await log.client_disconnected(connection)
        assert log.count == 0
        assert log.sessions == {}

    @pytest.mark.asyncio
    async def test_invalid_response(self):
        log = HTTPLog(io.StringIO())
        connection = Connection(Host(), Host())
        await log.client_data(connection, b"GET http://example.com/ HTTP/1.1\r\n\r\n")
        await log.server_data(connection, b"not http\r\n\r\n")
        await log.client_disconnected(connection)
        assert log.stream.getvalue() == "  ┊ GET http://example.com/ → (no response)\n"


@pytest.mark.parametrize("size, text", [(0, "0 B"), (999, "999 B"), (1500, "1.5 KB"), (2_500_000, "2.5 MB")])
def test_format_size(size, text):
    assert format_size(size) == text
