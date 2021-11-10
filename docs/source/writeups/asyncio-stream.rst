==========
Async mitm
==========

`mitm` is programmed on top of `asyncio's streams <https://docs.python.org/3/library/asyncio-stream.html>`_, and therefore is asynchronous by nature. This is a quick example on how to use `mitm` in an asyncio-based application.

Notice how the `mitm.mitm.MITM.start()` function works:

.. code-block:: python

    ...

    @staticmethod
    def start(config: Config = Config()):
        """
        Starts the MITM server.
        """

        async def start():
            server = await asyncio.start_server(
                lambda r, w: MITM(config=config).client_connect(r, w),
                host=config.host,
                port=config.port,
            )

            async with server:
                await server.serve_forever()

        logger.info("Booting up server on %s:%i." % (config.host, config.port))
        asyncio.run(start()) 

    ...

What the function does is start an asyncio server that creates a new :py:class:`mitm.mitm.MITM` instance on each client connection.

We can use this knowledge, then, to implement our own asyncio-based application where `mitm` runs in conjunction with our application. To do this, we would need to implement our own ``async start`` function. Here is a simple example using ``aiohttp``:

.. code-block:: python

    import asyncio
    import logging
    import aiohttp
    from mitm import MITM, Config

    async def start_mitm(config):
        """
        Starts the mitm server.
        """
        server = await asyncio.start_server(
            lambda r, w: MITM(config=config).client_connect(r, w),
            host=config.host,
            port=config.port,
        )

        await server.start_serving()
        return server

    async def send_request():
        """
        Sends request to example.com through mitm.
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://example.com",
                proxy="http://127.0.0.1:8888",
                ssl=False,
            ) as response:
                return response.status

    async def app():
        # Start the server with minimal logging.
        config = Config(log_level=logging.CRITICAL)
        server = await start_mitm(config)

        # Send a request.
        status = await send_request()
        print(f"The server replied with {status}!")

        # Close the server.
        await asyncio.sleep(1)
        server.close()
        await server.wait_closed()

    asyncio.run(app())
