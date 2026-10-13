import asyncio
import http.client
import json
import ssl

import pytest
from cryptography.hazmat.primitives import serialization

from mitm import MITM, HTTPLog, Middleware

from .conftest import HOST, client_context, request


async def logged(log, count=1):
    """
    Waits for the given number of requests to be logged, and returns them.
    """
    async with asyncio.timeout(5):
        while log.count < count:
            await asyncio.sleep(0.01)
    return [json.loads(line) for line in log.stream.getvalue().splitlines()]


async def send(proxy, data):
    """
    Sends raw data to the proxy, and returns everything it sends back until it closes.
    """
    reader, writer = await asyncio.open_connection(HOST, proxy.port)
    writer.write(data)
    response = await asyncio.wait_for(reader.read(), 5)
    writer.close()
    return response


class Test_HTTP:
    @pytest.mark.asyncio
    async def test_request(self, proxy, server, log):
        url = f"http://{HOST}:{server.port}/hello"
        assert await asyncio.to_thread(request, proxy, "GET", url) == (200, b"hello")

        [entry] = await logged(log)
        assert entry["request"]["method"] == "GET"
        assert entry["request"]["url"] == url
        assert entry["response"]["status"] == 200
        assert entry["response"]["body"] == "hello"
        assert entry["error"] is None

    @pytest.mark.asyncio
    async def test_response_until_close(self, proxy, server, log):
        url = f"http://{HOST}:{server.port}/close"
        assert await asyncio.to_thread(request, proxy, "GET", url) == (200, b"until close")

        [entry] = await logged(log)
        assert entry["response"]["body"] == "until close"

    @pytest.mark.asyncio
    async def test_unreachable(self, proxy, log):

        # Nothing listens on port 1, so the client is told the server cannot be reached.
        status, body = await asyncio.to_thread(request, proxy, "GET", f"http://{HOST}:1/")
        assert status == 502
        assert b"connection refused" in body

        [entry] = await logged(log)
        assert entry["request"]["url"] == f"http://{HOST}:1/"
        assert entry["error"] == f"Unable to connect to {HOST}:1 (connection refused)."


class Test_HTTPS:
    @pytest.mark.asyncio
    async def test_request(self, proxy, tls_server, log, ca_file):
        url = f"https://localhost:{tls_server.port}/hello"
        response = await asyncio.to_thread(request, proxy, "GET", url, context=client_context(ca_file))
        assert response == (200, b"hello")

        [entry] = await logged(log)
        assert entry["request"]["url"] == url
        assert entry["response"]["body"] == "hello"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method, path, body, expected",
        [
            ("POST", "/echo", b'{"a": 1}', '{"a": 1}'),
            ("GET", "/chunked", None, "first second"),
            ("GET", "/gzip", None, '{"compressed": true}'),
            ("GET", "/binary", None, None),
            ("HEAD", "/hello", None, ""),
        ],
    )
    async def test_bodies(self, proxy, tls_server, log, ca_file, method, path, body, expected):
        url = f"https://localhost:{tls_server.port}{path}"
        headers = {"Content-Type": "application/json"} if body else {}
        await asyncio.to_thread(request, proxy, method, url, body, headers, client_context(ca_file))

        [entry] = await logged(log)
        assert entry["response"]["body"] == expected
        if body:
            assert entry["request"]["body"] == body.decode()

    @pytest.mark.asyncio
    async def test_keep_alive(self, proxy, tls_server, log, ca_file):

        # Sends two requests through the same connection.
        def requests():
            connection = http.client.HTTPSConnection(HOST, proxy.port, context=client_context(ca_file))
            connection.set_tunnel(f"localhost:{tls_server.port}")
            for path in ("/hello", "/chunked"):
                connection.request("GET", path)
                connection.getresponse().read()
            connection.close()

        await asyncio.to_thread(requests)

        first, second = await logged(log, 2)
        assert first["request"]["url"].endswith("/hello")
        assert second["request"]["url"].endswith("/chunked")

    @pytest.mark.asyncio
    async def test_unreachable(self, proxy, log, ca_file):
        with pytest.raises(OSError, match="502"):
            await asyncio.to_thread(request, proxy, "GET", f"https://{HOST}:1/", context=client_context(ca_file))

        [entry] = await logged(log)
        assert entry["request"]["method"] == "CONNECT"
        assert "connection refused" in entry["error"]

    @pytest.mark.asyncio
    async def test_untrusted_by_client(self, proxy, tls_server, log):

        # The client does not trust the 'mitm' certificate authority.
        context = ssl.create_default_context()
        with pytest.raises(ssl.SSLCertVerificationError):
            await asyncio.to_thread(request, proxy, "GET", f"https://localhost:{tls_server.port}/", context=context)

        [entry] = await logged(log)
        assert "does not trust the mitm certificate authority" in entry["error"]

    @pytest.mark.asyncio
    async def test_untrusted_server(self, ca, tls_server, log, ca_file):

        # The 'mitm' does not trust the certificate of the server.
        async with MITM(port=0, certificate_authority=ca, middlewares=[log]) as mitm:
            url = f"https://localhost:{tls_server.port}/"
            with pytest.raises(OSError, match="502"):
                await asyncio.to_thread(request, mitm, "GET", url, context=client_context(ca_file))

        [entry] = await logged(log)
        assert "certificate verify failed" in entry["error"]


class Test_MITM:
    @pytest.mark.asyncio
    async def test_certificate_page(self, proxy, ca):
        assert b"200 OK" in await send(proxy, b"GET / HTTP/1.1\r\n\r\n")
        assert b"-----BEGIN CERTIFICATE-----" in await send(proxy, b"GET /cert.pem HTTP/1.1\r\n\r\n")

        # Certificates in DER format.
        for path in (b"/cert.cer", b"/cert.crt"):
            response = await send(proxy, b"GET %s HTTP/1.1\r\n\r\n" % path)
            assert response.endswith(ca.cert.public_bytes(serialization.Encoding.DER))

        assert (await send(proxy, b"GET /missing HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 404 Not Found")
        assert (await send(proxy, b"POST / HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 405 Method Not Allowed")

    @pytest.mark.asyncio
    async def test_request_to_itself(self, proxy, log):

        # The 'Host' points to the 'mitm' itself. If it were proxied, the 'mitm' would
        # connect to itself over and over again.
        response = await send(proxy, b"HEAD / HTTP/1.1\r\nHost: %s:%d\r\n\r\n" % (HOST.encode(), proxy.port))
        assert response.startswith(b"HTTP/1.1 200 OK")
        assert response.endswith(b"\r\n\r\n")
        assert len(proxy.connections) <= 1
        assert log.count == 0

    @pytest.mark.asyncio
    async def test_not_http(self, proxy, log):
        assert await send(proxy, b"\x16\x03\x01 not http\r\n\r\n") == b""

        [entry] = await logged(log)
        assert entry["error"] == "No protocol was found. Check the protocols list."

    @pytest.mark.asyncio
    async def test_stop(self, ca, server):
        mitm = MITM(port=0, certificate_authority=ca, middlewares=[Middleware()])
        await mitm.start()

        # Opens a connection, and leaves it open.
        reader, writer = await asyncio.open_connection(HOST, mitm.port)
        writer.write(b"GET http://%s:%d/hello HTTP/1.1\r\n\r\n" % (HOST.encode(), server.port))
        assert (await reader.readuntil(b"hello")).startswith(b"HTTP/1.1 200 OK")

        # Stopping the 'mitm' closes the connection.
        await asyncio.wait_for(mitm.stop(), 5)
        assert await asyncio.wait_for(reader.read(), 5) == b""
        assert mitm.server is None
        writer.close()

    @pytest.mark.asyncio
    async def test_defaults(self, data):
        mitm = MITM(port=0)
        assert [type(middleware) for middleware in mitm.middlewares] == [HTTPLog]

        # The certificate authority is stored, and loaded the next time.
        assert (data / "mitm.pem").exists()
        assert MITM().certificate_authority.cert == mitm.certificate_authority.cert

        # Port 0 is replaced by the port the 'mitm' listens on.
        async with mitm:
            assert mitm.port != 0

    @pytest.mark.asyncio
    async def test_middleware(self, ca, server):
        class Uppercase(Middleware):
            async def server_data(self, connection, data):
                return data.replace(b"hello", b"HELLO")

        async with MITM(port=0, certificate_authority=ca, middlewares=[Uppercase]) as mitm:
            url = f"http://{HOST}:{server.port}/hello"
            assert await asyncio.to_thread(request, mitm, "GET", url) == (200, b"HELLO")
