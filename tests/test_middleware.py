import io
import json
import logging

import pytest

from mitm import Connection, Host, HTTPLog, Log, Middleware
from mitm.http import Exchange, parse_head


def exchange(request: bytes, response: bytes | None, duration: float = 0.25) -> Exchange:
    request_head, _, request_body = request.partition(b"\r\n\r\n")
    message = parse_head(request_head)
    message.body, message.size, message.complete = request_body, len(request_body), True
    result = Exchange(message, url="https://example.com" + message.target, started=1_700_000_000.0)
    if response is not None:
        head, _, body = response.partition(b"\r\n\r\n")
        result.response = parse_head(head)
        result.response.body, result.response.size, result.response.complete = body, len(body), True
        result.ended = result.started + duration
    return result


RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n\r\n" + b'{"ok": true}'


class TestHTTPLog:
    def write(self, *exchanges, **options) -> str:
        log = HTTPLog(io.StringIO(), **options)
        log.write(*exchanges)
        assert log.count == len(exchanges)
        return log.stream.getvalue()

    def test_summary(self):
        output = self.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", RESPONSE))
        assert output == "  ┊ GET https://example.com/a → 200 OK (application/json, 12 B, 250 ms)\n"

    def test_summary_no_response(self):
        output = self.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", None))
        assert output == "  ┊ GET https://example.com/a → (no response)\n"

    def test_error(self):
        failed = exchange(b"GET /a HTTP/1.1\r\n\r\n", None)
        failed.error = "cannot connect"
        assert self.write(failed) == "  ┊ GET https://example.com/a ✗ cannot connect\n"

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

    def test_verbose_binary_and_truncated(self):
        binary = b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\n\r\n\x89PNG"
        output = self.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", binary), verbose=True)
        assert "  ┊ <4 B binary, image/png>\n" in output

        output = self.write(exchange(b"POST /a HTTP/1.1\r\n\r\n" + b"x" * 10, None), verbose=True, max_body=4)
        assert "  ┊ xxxx\n  ┊ … truncated (10 B received)\n" in output
        assert "(no response)" in output

    def test_json(self):
        [line] = self.write(exchange(b"GET /a HTTP/1.1\r\nAccept: */*\r\n\r\n", RESPONSE), json=True).splitlines()
        assert json.loads(line) == {
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

    def test_color_only_on_terminals(self, monkeypatch):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

        log = HTTPLog(Terminal())
        log.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", RESPONSE))
        assert log.stream.getvalue().startswith("\x1b[2m")

        monkeypatch.setenv("NO_COLOR", "1")
        log = HTTPLog(Terminal())
        log.write(exchange(b"GET /a HTTP/1.1\r\n\r\n", RESPONSE))
        assert log.stream.getvalue().startswith("  ┊")

    async def test_ignores_non_http(self):
        log = HTTPLog(io.StringIO())
        connection = Connection(Host(), Host())
        assert await log.client_data(connection, b"\x16\x03\x01 tls\r\n\r\n") == b"\x16\x03\x01 tls\r\n\r\n"
        assert await log.server_data(connection, b"more") == b"more"
        await log.client_disconnected(connection)
        assert log.count == 0
        assert log.sessions == {}

    async def test_upgrade_and_bad_response(self):
        log = HTTPLog(io.StringIO())
        connection = Connection(Host(), Host())
        await log.client_data(connection, b"GET http://example.com/ HTTP/1.1\r\n\r\n")
        await log.server_data(connection, b"not http\r\n\r\n")
        await log.client_disconnected(connection)
        assert log.stream.getvalue() == "  ┊ GET http://example.com/ → (no response)\n"


async def test_middleware_defaults():
    middleware, connection = Middleware(), Connection(Host(), Host())
    assert repr(middleware) == "Middleware(Middleware)"
    assert await middleware.client_data(connection, b"data") == b"data"
    assert await middleware.server_data(connection, b"data") == b"data"
    for hook in ("client_connected", "server_connected", "client_disconnected", "server_disconnected"):
        assert await getattr(middleware, hook)(connection) is None
    assert await middleware.connection_error(connection, OSError()) is None


async def test_log(caplog):
    log, connection = Log(), Connection(Host(), Host())
    with caplog.at_level(logging.INFO, logger="mitm"):
        await log.mitm_started("127.0.0.1", 8888)
        await log.client_connected(connection)
        assert await log.client_data(connection, b"line one\r\nline two") == b"line one\r\nline two"
        await log.server_connected(connection)
        assert await log.server_data(connection, b"\xff") == b"\xff"
        await log.server_disconnected(connection)
        await log.client_disconnected(connection)
        await log.connection_error(connection, OSError("boom"))
    assert "MITM server started on 127.0.0.1:8888." in caplog.text
    assert "line one\n\tline two" in caplog.text
    assert "b'\\xff'" in caplog.text
    assert "boom" in caplog.text


@pytest.mark.parametrize(("size", "text"), [(0, "0 B"), (999, "999 B"), (1500, "1.5 KB"), (2_500_000, "2.5 MB")])
def test_format_size(size, text):
    from mitm.extension.middleware import format_size

    assert format_size(size) == text
