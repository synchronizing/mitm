import asyncio

import pytest

import mitm

HOST = "127.0.0.1"
PORT = 8888
BUFFER_SIZE = 1024


@pytest.fixture(autouse=True, scope="session")
def server():
    loop = asyncio.new_event_loop()
    mitm_ = mitm.MITM(host=HOST, port=PORT)

    async def run():
        await mitm_.start()
        await mitm_.server.serve_forever()

    task = loop.create_task(run())
    loop.run_until_complete(asyncio.sleep(0.5))

    try:
        yield
    finally:
        task.cancel()
        loop.run_until_complete(mitm_.stop())
        loop.close()
