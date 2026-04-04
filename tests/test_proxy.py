import asyncio

import pytest

from .conftest import BUFFER_SIZE, HOST, PORT


class Test_ServeDirect:
    @pytest.mark.asyncio
    async def test_root_returns_html(self):
        reader, writer = await asyncio.open_connection(HOST, PORT)
        writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await reader.read(BUFFER_SIZE)
        assert data.startswith(b"HTTP/1.1 200 OK")
        assert b"text/html" in data
        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_cert_pem_returns_pem(self):
        reader, writer = await asyncio.open_connection(HOST, PORT)
        writer.write(b"GET /cert.pem HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await reader.read(BUFFER_SIZE)
        assert data.startswith(b"HTTP/1.1 200 OK")
        assert b"pem" in data.lower()
        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_cert_cer_returns_cert(self):
        reader, writer = await asyncio.open_connection(HOST, PORT)
        writer.write(b"GET /cert.cer HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await reader.read(BUFFER_SIZE)
        assert data.startswith(b"HTTP/1.1 200 OK")
        assert b"x509" in data.lower()
        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_cert_crt_returns_cert(self):
        reader, writer = await asyncio.open_connection(HOST, PORT)
        writer.write(b"GET /cert.crt HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await reader.read(BUFFER_SIZE)
        assert data.startswith(b"HTTP/1.1 200 OK")
        assert b"x509" in data.lower()
        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_unknown_path_returns_404(self):
        reader, writer = await asyncio.open_connection(HOST, PORT)
        writer.write(b"GET /nonexistent HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()
        data = await reader.read(BUFFER_SIZE)
        assert data.startswith(b"HTTP/1.1 200 OK")
        assert b"404 Not Found" in data
        writer.close()
        await writer.wait_closed()


class Test_MITM_Lifecycle:
    @pytest.mark.asyncio
    async def test_context_manager(self):
        import mitm as mitm_module

        m = mitm_module.MITM(host="127.0.0.1", port=18889)
        async with m:
            assert m.server is not None
            reader, writer = await asyncio.open_connection("127.0.0.1", 18889)
            writer.close()
            await writer.wait_closed()
        assert m.server is None

    @pytest.mark.asyncio
    async def test_stop_frees_port(self):
        import mitm as mitm_module

        m = mitm_module.MITM(host="127.0.0.1", port=18890)
        await m.start()
        assert m.server is not None
        await m.stop()
        assert m.server is None
