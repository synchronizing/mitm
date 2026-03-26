import pytest

from mitm import extension, models
from mitm.extension.middleware import CLILog, format_bytes, format_gutter


class Test_Log:
    log = extension.Log()
    connection = models.Connection(models.Host(), models.Host())

    @pytest.mark.asyncio
    async def test_init(self):
        log = extension.Log()
        assert repr(log) == "Middleware(Log)"

    @pytest.mark.asyncio
    async def test_mitm_started(self):
        await self.log.mitm_started("localhost", 80)

    @pytest.mark.asyncio
    async def test_client_connected(self):
        await self.log.client_connected(self.connection)

    @pytest.mark.asyncio
    async def test_server_connected(self):
        await self.log.server_connected(self.connection)

    @pytest.mark.asyncio
    async def test_client_data(self):
        data = b"hello"
        ret = await self.log.client_data(self.connection, data)
        assert ret == data

    @pytest.mark.asyncio
    async def test_server_data(self):
        data = b"hello"
        ret = await self.log.server_data(self.connection, data)
        assert ret == data

    @pytest.mark.asyncio
    async def test_client_disconnected(self):
        await self.log.client_disconnected(self.connection)

    @pytest.mark.asyncio
    async def test_server_disconnected(self):
        await self.log.server_disconnected(self.connection)


class Test_FormatBytes:
    def test_valid_utf8(self):
        result = format_bytes(b"hello world")
        assert result == "hello world"

    def test_multiline(self):
        result = format_bytes(b"line1\r\nline2")
        assert result == "line1\n\tline2"

    def test_invalid_utf8(self):
        data = b"hello\xff"
        result = format_bytes(data)
        assert result == repr(data)

    def test_empty(self):
        result = format_bytes(b"")
        assert result == ""


class Test_FormatGutter:
    def test_valid_utf8(self):
        result = format_gutter(b"GET / HTTP/1.1")
        assert "┊" in result
        assert "GET / HTTP/1.1" in result

    def test_multiline(self):
        result = format_gutter(b"line1\r\nline2")
        assert result.count("┊") == 2
        assert "line1" in result
        assert "line2" in result

    def test_invalid_utf8(self):
        data = b"binary\xff"
        result = format_gutter(data)
        assert "┊" in result
        assert repr(data) in result

    def test_empty(self):
        result = format_gutter(b"")
        assert result == ""


class Test_CLILog:
    cli_log = CLILog()
    connection = models.Connection(models.Host(), models.Host())

    @pytest.mark.asyncio
    async def test_mitm_started(self, capsys):
        await self.cli_log.mitm_started("127.0.0.1", 8888)
        captured = capsys.readouterr()
        assert "127.0.0.1" in captured.err
        assert "8888" in captured.err

    @pytest.mark.asyncio
    async def test_server_connected(self, capsys):
        await self.cli_log.server_connected(self.connection)
        captured = capsys.readouterr()
        assert str(self.connection.server) in captured.err

    @pytest.mark.asyncio
    async def test_client_data(self, capsys):
        data = b"GET / HTTP/1.1"
        ret = await self.cli_log.client_data(self.connection, data)
        captured = capsys.readouterr()
        assert "GET / HTTP/1.1" in captured.err
        assert ret == data

    @pytest.mark.asyncio
    async def test_server_data(self, capsys):
        data = b"HTTP/1.1 200 OK"
        ret = await self.cli_log.server_data(self.connection, data)
        captured = capsys.readouterr()
        assert "HTTP/1.1 200 OK" in captured.err
        assert ret == data

    @pytest.mark.asyncio
    async def test_client_connected_noop(self, capsys):
        ret = await self.cli_log.client_connected(self.connection)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert ret is None

    @pytest.mark.asyncio
    async def test_client_disconnected_noop(self, capsys):
        ret = await self.cli_log.client_disconnected(self.connection)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert ret is None

    @pytest.mark.asyncio
    async def test_server_disconnected_noop(self, capsys):
        ret = await self.cli_log.server_disconnected(self.connection)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert ret is None
