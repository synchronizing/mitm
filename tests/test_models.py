import asyncio

import pytest

from mitm import Connection, Host


@pytest.mark.asyncio
async def test_Host():
    host = Host()
    assert bool(host) is False
    assert str(host) == "<empty host>"
    assert host.host is None
    assert host.port is None

    # Use a local loopback server to get a real reader/writer pair.
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)

    host = Host(reader=reader, writer=writer, mitm_managed=False)
    assert bool(host)
    assert host.host == "127.0.0.1"
    assert host.port == port
    assert str(host) == f"127.0.0.1:{port}"
    assert repr(host) == f"Host(127.0.0.1:{port}, mitm_managed=False)"

    # Waits for the server to close the connection, so it is not left open.
    assert await reader.read() == b""
    writer.close()
    server.close()
    await server.wait_closed()


def test_Connection():
    connection = Connection(client=Host(), server=Host())
    assert repr(connection) == "Connection(client=<empty host>, server=<empty host>, protocol=None)"
