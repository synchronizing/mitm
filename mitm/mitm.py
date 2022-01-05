""" 
Man-in-the-middle.
"""

import asyncio
import logging
import ssl
from typing import List

from toolbox.asyncio.pattern import CoroutineClass

from . import __data__, crypto, middleware, protocol
from .core import Connection, Flow, Host

logger = logging.getLogger(__package__)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)


class MITM(CoroutineClass):
    """
    Man-in-the-middle server.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8888,
        protocols: List[protocol.Protocol] = [protocol.HTTP],
        middlewares: List[middleware.Middleware] = [middleware.Log],
        buffer_size: int = 8192,
        timeout: int = 5,
        ssl_context: ssl.SSLContext = crypto.mitm_ssl_default_context(),
        run: bool = False,
    ):
        """
        Initializes the MITM class.

        Args:
            host: Host to listen on. Defaults to `127.0.0.1`.
            port: Port to listen on. Defaults to `8888`.
            protocols: List of protocols to use. Defaults to `[protocol.HTTP]`.
            middlewares: List of middlewares to use. Defaults to `[middleware.Log]`.
            buffer_size: Buffer size to use. Defaults to `8192`.
            timeout: Timeout to use. Defaults to `5`.
            ssl_context: SSL context to use. Defaults to `crypto.mitm_ssl_default_context()`.
            run: Whether to start the server immediately. Defaults to `False`.

        Example:

            .. code-block:: python

                from mitm import MITM

                mitm = MITM()
                mitm.run()
        """
        self.host = host
        self.port = port
        self.middlewares = middlewares
        self.protocols = protocols
        self.buffer_size = buffer_size
        self.timeout = timeout
        self.ssl_context = ssl_context
        super().__init__(run=run)

    async def entry(self):
        """
        Runs the MITM server.
        """
        try:
            server = await asyncio.start_server(
                lambda reader, writer: self.mitm(
                    Connection(
                        client=Host(reader=reader, writer=writer),
                        server=Host(),
                        ssl_context=self.ssl_context,
                    )
                ),
                host=self.host,
                port=self.port,
            )
        except OSError as e:
            self._loop.stop()
            raise e

        for mw in self.middlewares:
            await mw.mitm_started(host=self.host, port=self.port)

        async with server:
            await server.serve_forever()

    async def mitm(self, connection: Connection):
        """
        Handles a single connection.

        This method is called by the asyncio server when a new connection is
        established. The connection is passed to the middlewares at different points
        in the process, as well as the protocols when attempting to resolve the
        destination server.

        Warning:
            This method is not intended to be called directly.
        """

        async def _relay(connection: Connection, event: asyncio.Event, flow: Flow):
            """
            Forwards data between two connections.
            """

            if flow == Flow.CLIENT_TO_SERVER:
                reader = connection.client.reader
                writer = connection.server.writer
            elif flow == Flow.SERVER_TO_CLIENT:
                reader = connection.server.reader
                writer = connection.client.writer

            while not event.is_set() and not reader.at_eof():
                data = None
                try:
                    data = await asyncio.wait_for(
                        reader.read(self.buffer_size),
                        self.timeout,
                    )
                except asyncio.exceptions.TimeoutError:
                    pass

                if not data:
                    event.set()
                    break
                else:

                    # Pass data through middlewares.
                    for mw in self.middlewares:
                        if flow == Flow.SERVER_TO_CLIENT:
                            data = await mw.server_data(connection, data)
                        elif flow == Flow.CLIENT_TO_SERVER:
                            data = await mw.client_data(connection, data)

                    writer.write(data)
                    await writer.drain()

        # Runs initial middlewares.
        for mw in self.middlewares:
            await mw.client_connected(connection=connection)

        # Gets the bytes needed to identify the protocol.
        min_bytes_needed = max(proto.bytes_needed for proto in self.protocols)
        data = await connection.client.reader.read(n=min_bytes_needed)

        # Calls middleware on initial data.
        for mw in self.middlewares:
            await mw.client_data(connection=connection, data=data)

        # Finds the protocol that matches the data.
        for proto in self.protocols:
            try:
                connected = await proto.connect(connection=connection, data=data)
                if connected:
                    break
            except protocol.InvalidProtocol:
                connected = False

        # Server connected successfully.
        if connected:

            # Calls middlewares for server connected.
            for mw in self.middlewares:
                await mw.server_connected(connection=connection)

            # Relays data between client/server.
            event = asyncio.Event()
            await asyncio.gather(
                _relay(connection, event, Flow.SERVER_TO_CLIENT),
                _relay(connection, event, Flow.CLIENT_TO_SERVER),
            )

        # Close connections.
        if not connection.client.writer.is_closing():
            connection.client.writer.close()
            await connection.client.writer.wait_closed()

        if connection.server and connection.server.writer.is_closing():
            connection.server.writer.close()
            await connection.server.writer.wait_closed()

        for mw in self.middlewares:
            await mw.client_disconnected(connection=connection)
            if connection.server:
                await mw.server_disconnected(connection=connection)
