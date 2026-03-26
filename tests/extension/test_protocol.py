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


class Test_HTTP_Resolve:
    http = HTTP()

    @pytest.mark.asyncio
    async def test_connect_request(self):
        connection = Connection(Host(), Host())
        data = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n"
        host, port, tls = await self.http.resolve(connection, data)
        assert host == "example.com"
        assert port == 443
        assert tls is True

    @pytest.mark.asyncio
    async def test_get_with_host_header(self):
        connection = Connection(Host(), Host())
        data = b"GET /path HTTP/1.1\r\nHost: example.com\r\n\r\n"
        host, port, tls = await self.http.resolve(connection, data)
        assert host == "example.com"
        assert port == 80
        assert tls is False

    @pytest.mark.asyncio
    async def test_missing_host_header_raises(self):
        connection = Connection(Host(), Host())
        data = b"GET /path HTTP/1.1\r\n\r\n"
        with pytest.raises(InvalidProtocol):
            await self.http.resolve(connection, data)


class Test_HTTP_Connect:
    http = HTTP()

    @pytest.mark.asyncio
    async def test_connect_no_tls_populates_server(self):
        connection = Connection(Host(), Host())
        data = b"GET / HTTP/1.1\r\nHost: google.com\r\n\r\n"
        host, port, tls = await self.http.resolve(connection, data)
        await self.http.connect(connection, host, port, tls, data)
        assert connection.server.reader is not None
        assert connection.server.writer is not None
        connection.server.writer.close()
