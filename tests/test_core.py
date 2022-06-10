import pytest
from mitm import Host, Connection
import asyncio


@pytest.mark.asyncio
async def test_Host():

    host = Host()
    assert bool(host) is False
    assert str(host) == "<empty host>"

    # 93.184.216.34 = Example.com
    reader, writer = await asyncio.open_connection("93.184.216.34", 80)
    host = Host(reader=reader, writer=writer, mitm_managed=False)
    assert host.host == "93.184.216.34"
    assert host.port == 80
    assert bool(host)
    assert str(host) == "93.184.216.34:80"


@pytest.mark.asyncio
async def test_Connection():
    host1 = Host()
    host2 = Host()
    connection = Connection(client=host1, server=host2)
    assert repr(connection) == "Connection(client=<empty host>, server=<empty host>, protocol=None)"
