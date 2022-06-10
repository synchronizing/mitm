import mitm
import pytest
import asyncio

HOST = "127.0.0.1"
PORT = 8888
BUFFER_SIZE = 1024


async def start():
    """
    Starts the MITM server.
    """
    loop = asyncio.get_event_loop()
    mitm_ = mitm.MITM()
    try:
        srv = await asyncio.start_server(
            lambda reader, writer: mitm_.mitm(
                mitm.Connection(
                    client=mitm.Host(reader=reader, writer=writer),
                    server=mitm.Host(),
                )
            ),
            host=HOST,
            port=PORT,
        )
    except OSError as e:
        loop.stop()
        raise e

    async with srv:
        await srv.serve_forever()


@pytest.fixture(scope="session")
def event_loop():
    return asyncio.get_event_loop()


@pytest.fixture(autouse=True, scope="session")
def server(event_loop):
    task = asyncio.ensure_future(start(), loop=event_loop)
    # Sleeps to allow the server to start.
    event_loop.run_until_complete(asyncio.sleep(1))

    try:
        yield
    finally:
        task.cancel()
