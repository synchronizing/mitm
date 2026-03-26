import asyncio
import threading
import time

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

    def serve():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run())

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    time.sleep(0.5)

    yield

    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.run_until_complete(mitm_.stop())
    loop.close()
