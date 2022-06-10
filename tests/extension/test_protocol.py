import asyncio

import pytest
from mitm import HTTP, Connection, Host, InvalidProtocol


class Test_HTTP:
    HTTP = HTTP()

    def test_init(self):
        assert self.HTTP.bytes_needed
        assert self.HTTP.buffer_size
        assert self.HTTP.timeout
        assert self.HTTP.keep_alive

    @pytest.mark.asyncio
    async def test_resolve(self):
        connection = Connection(Host(), Host())
        data = b"GET / HTTP/1.1\r\nHost: google.com\r\n\r\n"
        host, port, tls = await self.HTTP.resolve(connection, data)
        assert host == "google.com"
        assert port == 80
        assert not tls

        with pytest.raises(InvalidProtocol):
            data = b"junk data"
            await self.HTTP.resolve(connection, data)

    @pytest.mark.asyncio
    async def test_connect_no_tls(self):
        connection = Connection(Host(), Host())
        data = b"GET / HTTP/1.1\r\nHost: google.com\r\n\r\n"
        host, port, tls = await self.HTTP.resolve(connection, data)

        # Connects to the host, port.
        await self.HTTP.connect(connection, host, port, tls, data)

        # Checks if we connected to the host, port.
        assert connection.server.reader
        assert connection.server.writer
