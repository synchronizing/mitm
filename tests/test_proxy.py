import asyncio
import json
import ssl

import pytest

import mitm
from mitm import MITM, Connection, Host, HTTPLog, Middleware

from .conftest import client_context, request


async def records(log: HTTPLog, count: int = 1) -> list[dict]:
    """
    Waits for `log` to hold `count` exchanges, and returns them.
    """
    async with asyncio.timeout(5):
        while log.count < count:
            await asyncio.sleep(0.01)
    return [json.loads(line) for line in log.stream.getvalue().splitlines()]


async def raw(proxy: MITM, data: bytes) -> bytes:
    """
    Sends raw bytes to the proxy and returns everything it answers until it closes.
    """
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    writer.write(data)
    response = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    return response


class TestHTTP:
    async def test_get(self, proxy, origin, log):
        url = f"http://127.0.0.1:{origin.port}/hello"
        assert await asyncio.to_thread(request, proxy, "GET", url) == (200, b"hello")

        [record] = await records(log)
        assert record["request"]["method"] == "GET"
        assert record["request"]["url"] == url
        assert record["response"]["status"] == 200
        assert record["response"]["body"] == "hello"
        assert record["error"] is None

    async def test_close_delimited(self, proxy, origin, log):
        url = f"http://127.0.0.1:{origin.port}/close"
        assert await asyncio.to_thread(request, proxy, "GET", url) == (200, b"until close")
        [record] = await records(log)
        assert record["response"]["body"] == "until close"

    async def test_unreachable(self, proxy, log):
        status, body = await asyncio.to_thread(request, proxy, "GET", "http://127.0.0.1:1/")
        assert status == 502
        assert b"connection refused" in body

        [record] = await records(log)
        assert record["request"]["url"] == "http://127.0.0.1:1/"
        assert "cannot connect to 127.0.0.1:1: connection refused" in record["error"]


class TestHTTPS:
    async def test_get(self, proxy, tls_origin, log, ca_file):
        url = f"https://localhost:{tls_origin.port}/hello"
        assert await asyncio.to_thread(request, proxy, "GET", url, context=client_context(ca_file)) == (200, b"hello")
        [record] = await records(log)
        assert record["request"]["url"] == url
        assert record["response"]["body"] == "hello"

    @pytest.mark.parametrize(
        ("method", "path", "body", "expected"),
        [
            ("POST", "/echo", b'{"a": 1}', '{"a": 1}'),
            ("GET", "/chunked", None, "first second"),
            ("GET", "/gzip", None, '{"compressed": true}'),
            ("GET", "/binary", None, None),
            ("HEAD", "/hello", None, ""),
        ],
    )
    async def test_bodies(self, proxy, tls_origin, log, ca_file, method, path, body, expected):
        url = f"https://localhost:{tls_origin.port}{path}"
        headers = {"Content-Type": "application/json"} if body else {}
        await asyncio.to_thread(request, proxy, method, url, body, headers, client_context(ca_file))
        [record] = await records(log)
        assert record["response"]["body"] == expected
        if body:
            assert record["request"]["body"] == body.decode()

    async def test_keep_alive(self, proxy, tls_origin, log, ca_file):
        import http.client

        def two_requests():
            connection = http.client.HTTPSConnection("127.0.0.1", proxy.port, context=client_context(ca_file))
            connection.set_tunnel(f"localhost:{tls_origin.port}")
            for path in ("/hello", "/chunked"):
                connection.request("GET", path)
                connection.getresponse().read()
            connection.close()

        await asyncio.to_thread(two_requests)
        first, second = await records(log, 2)
        assert first["request"]["url"].endswith("/hello")
        assert second["request"]["url"].endswith("/chunked")

    async def test_unreachable(self, proxy, log, ca_file):
        with pytest.raises(OSError, match="502"):
            await asyncio.to_thread(request, proxy, "GET", "https://127.0.0.1:1/", context=client_context(ca_file))
        [record] = await records(log)
        assert record["request"]["method"] == "CONNECT"
        assert "connection refused" in record["error"]

    async def test_client_rejects_certificate(self, proxy, tls_origin, log):
        with pytest.raises(ssl.SSLCertVerificationError):
            await asyncio.to_thread(
                request, proxy, "GET", f"https://localhost:{tls_origin.port}/", context=ssl.create_default_context()
            )
        [record] = await records(log)
        assert "does not trust the mitm CA" in record["error"]

    async def test_server_certificate_untrusted(self, ca, tls_origin, log, ca_file):
        async with MITM(port=0, certificate_authority=ca, middlewares=[log]) as proxy:
            with pytest.raises(OSError, match="502"):
                await asyncio.to_thread(
                    request, proxy, "GET", f"https://localhost:{tls_origin.port}/", context=client_context(ca_file)
                )
        [record] = await records(log)
        assert "certificate verify failed" in record["error"]


class TestMITM:
    async def test_certificate_page(self, proxy, ca):
        assert b"200 OK" in await raw(proxy, b"GET / HTTP/1.1\r\n\r\n")
        assert b"-----BEGIN CERTIFICATE-----" in await raw(proxy, b"GET /cert.pem HTTP/1.1\r\n\r\n")
        for path in (b"/cert.cer", b"/cert.crt"):
            response = await raw(proxy, b"GET %s HTTP/1.1\r\n\r\n" % path)
            assert response.endswith(ca.cert.public_bytes(mitm.crypto.serialization.Encoding.DER))
        assert (await raw(proxy, b"GET /missing HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 404 Not Found")
        assert (await raw(proxy, b"POST / HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 405 Method Not Allowed")

    async def test_requests_to_itself_are_not_forwarded(self, proxy, log):
        """
        A `Host` naming the proxy must not make it connect to itself, again and again.
        """
        response = await raw(proxy, b"HEAD / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\n\r\n" % proxy.port)
        assert response.startswith(b"HTTP/1.1 200 OK") and response.endswith(b"\r\n\r\n")
        assert len(proxy.connections) <= 1
        assert log.count == 0

    async def test_not_http(self, proxy, log):
        assert await raw(proxy, b"\x16\x03\x01 not http\r\n\r\n") == b""
        [record] = await records(log)
        assert "no protocol matched" in record["error"]

    async def test_stop_closes_open_connections(self, ca, origin):
        proxy = MITM(port=0, certificate_authority=ca, middlewares=[Middleware()])
        await proxy.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        writer.write(b"GET http://127.0.0.1:%d/hello HTTP/1.1\r\n\r\n" % origin.port)
        assert (await reader.readuntil(b"hello")).startswith(b"HTTP/1.1 200 OK")

        await asyncio.wait_for(proxy.stop(), 5)
        assert await asyncio.wait_for(reader.read(), 5) == b""
        assert proxy.server is None
        writer.close()

    async def test_defaults(self, data):
        proxy = MITM(port=0)
        assert [type(m) for m in proxy.middlewares] == [HTTPLog]
        assert (data / "mitm.pem").exists()
        assert MITM().certificate_authority.cert == proxy.certificate_authority.cert
        async with proxy:
            assert proxy.port != 0

    async def test_middleware_modifies_data(self, ca, ca_file, origin):
        class Uppercase(Middleware):
            async def server_data(self, connection, data):
                return data.replace(b"hello", b"HELLO")

        async with MITM(port=0, certificate_authority=ca, middlewares=[Uppercase]) as proxy:
            url = f"http://127.0.0.1:{origin.port}/hello"
            assert await asyncio.to_thread(request, proxy, "GET", url) == (200, b"HELLO")


async def test_host():
    assert not Host()
    assert str(Host()) == "<empty host>"
    assert repr(Connection(Host(), Host())) == "Connection(client=<empty host>, server=<empty host>, protocol=None)"

    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    host = Host(reader, writer)
    assert (host.host, host.port, str(host)) == ("127.0.0.1", port, f"127.0.0.1:{port}")
    assert await reader.read() == b""  # The server accepted, and closed, the connection.
    writer.close()
    server.close()
    await server.wait_closed()
