import pytest
from mitm import extension, core


class Test_Log:
    log = extension.Log()
    connection = core.Connection(core.Host(), core.Host())

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
