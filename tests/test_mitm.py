import asyncio
import pytest


from .conftest import HOST, PORT, BUFFER_SIZE


@pytest.mark.asyncio
async def test_connection():
    reader, writer = await asyncio.open_connection(HOST, PORT)
    assert reader
    assert writer
    writer.close()


@pytest.mark.asyncio
async def test_http_request():
    reader, writer = await asyncio.open_connection(HOST, PORT)
    writer.write(b"GET / HTTP/1.1\r\nHost: example.com\r\n\r\n")
    data = await reader.read(BUFFER_SIZE)
    assert data.startswith(b"HTTP/1.1 200 OK\r\n")
    writer.close()
    await writer.wait_closed()


@pytest.mark.asyncio
async def test_https_request():
    reader, writer = await asyncio.open_connection(HOST, PORT)
    writer.write(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com\r\n\r\n")
    data = await reader.read(BUFFER_SIZE)
    assert data.startswith(b"HTTP/1.1 200 OK\r\n")
    writer.close()
    await writer.wait_closed()
