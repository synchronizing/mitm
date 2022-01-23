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
        keep_alive: bool = True,
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
            keep_alive: Whether to keep the connection alive. Defaults to `True`.
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
        self.keep_alive = keep_alive
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
        Handles an incoming connection.

        Warning:
            This method is not intended to be called directly.
        """

        async def _relay(connection: Connection, event: asyncio.Event, flow: Flow):
            """
            Forwards data between two hosts in a Connection.
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

        #  Calls middlewares for client initial connect.
        for mw in self.middlewares:
            await mw.client_connected(connection=connection)

        # Gets the bytes needed to identify the protocol.
        min_bytes_needed = max(proto.bytes_needed for proto in self.protocols)
        data = await connection.client.reader.read(n=min_bytes_needed)

        # Calls middleware on client's data.
        for mw in self.middlewares:
            await mw.client_data(connection=connection, data=data)

        # Finds the protocol that matches the data, and connects to the server.
        found = False
        for proto in self.protocols:
            try:
                found = await proto.connect(connection=connection, data=data)
                if found:
                    break
            except protocol.InvalidProtocol:
                pass

        # Protocol was found, and we connected to a server.
        if found:
            for mw in self.middlewares:
                await mw.server_connected(connection=connection)

            # Keeps the connection alive until the client or server closes it.
            run_once = True
            while (
                not connection.client.reader.at_eof()
                and not connection.server.reader.at_eof()
                and (self.keep_alive or run_once)
            ):

                # Keeps trying to relay data until the connection closes.
                event = asyncio.Event()
                await asyncio.gather(
                    _relay(connection, event, Flow.SERVER_TO_CLIENT),
                    _relay(connection, event, Flow.CLIENT_TO_SERVER),
                )

                # Run the while loop only one iteration if keep_alive is False.
                run_once = False

        # If a server connection exists, we close it too.
        if connection.server:
            connection.server.writer.close()
            await connection.server.writer.wait_closed()

            # Calls the server's 'disconnected' middleware.
            for mw in self.middlewares:
                await mw.server_disconnected(connection=connection)

        # Attempts to disconnect with the client.
        # In some instances 'wait_closed()' might hang. This is a knowm issue that
        # happens when and if the client keeps the connection alive, and, unfortunately,
        # there is nothing we can do about it. This is a reported bug.
        # https://bugs.python.org/issue39758
        connection.client.writer.close()
        await connection.client.writer.wait_closed()

        # Calls the client 'disconnected' middleware.
        for mw in self.middlewares:
            await mw.client_disconnected(connection=connection)
