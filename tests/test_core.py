import asyncio

import pytest

from mitm import Connection, Host


@pytest.mark.asyncio
async def test_Host():

    host = Host()
    assert bool(host) is False
    assert str(host) == "<empty host>"

    # Use a local loopback server to get a real reader/writer pair.
    srv = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    addr = srv.sockets[0].getsockname()
    reader, writer = await asyncio.open_connection(addr[0], addr[1])
    host = Host(reader=reader, writer=writer, mitm_managed=False)
    assert host.host == "127.0.0.1"
    assert host.port == addr[1]
    assert bool(host)
    assert str(host) == f"127.0.0.1:{addr[1]}"
    writer.close()
    srv.close()


@pytest.mark.asyncio
async def test_Connection():
    host1 = Host()
    host2 = Host()
    connection = Connection(client=host1, server=host2)
    assert repr(connection) == "Connection(client=<empty host>, server=<empty host>, protocol=None)"
