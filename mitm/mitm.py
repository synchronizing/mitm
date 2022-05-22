"""
Man-in-the-middle.
"""

import asyncio
import logging
from typing import List

from toolbox.asyncio.pattern import CoroutineClass

from . import __data__, middleware, protocol
from .core import Connection, Flow, Host
from .crypto import CertificateAuthority

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
        ca: CertificateAuthority = None,
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
            ca: Certificate authority to use. Defaults to `CertificateAuthority()`.
            run: Whether to start the server immediately. Defaults to `False`.

        Example:

            .. code-block:: python

                from mitm import MITM

                mitm = MITM()
                mitm.run()
        """
        self.host = host
        self.port = port
        self.protocols = protocols
        self.buffer_size = buffer_size
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.ca = ca if ca else CertificateAuthority()

        # Stores the CA certificate and private key.
        cert_path, key_path = __data__ / "mitm.crt", __data__ / "mitm.key"
        self.ca.save(cert_path=cert_path, key_path=key_path)

        # Initialize any middleware that is not already initialized.
        new_middleware = []
        for middleware in middlewares:
            if isinstance(middleware, type):
                middleware = middleware()
            new_middleware.append(middleware)
        self.middlewares = new_middleware

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
        found, proto = False, None
        for protocol in self.protocols:
            try:
                found = await protocol.connect(connection=connection, data=data, ca=self.ca)
                if found:
                    proto = protocol
                    break
            except protocol.InvalidProtocol:
                pass

        # Protocol was found, and we connected to a server.
        if found and connection.server:

            # Calls middleware for server initial connect.
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
        elif found and not connection.server:
            raise ValueError(
                "The protocol was found, but the server was not connected. "
                f"Check the {proto.__class__.__name__} implementation."
            )

        # If a server connection exists, we close it.
        if connection.server and connection.server.mitm_managed:
            connection.server.writer.close()
            await connection.server.writer.wait_closed()

            # Calls the server's 'disconnected' middleware.
            for mw in self.middlewares:
                await mw.server_disconnected(connection=connection)

        # Attempts to disconnect with the client.
        # In some instances 'wait_closed()' might hang. This is a known issue that
        # happens when and if the client keeps the connection alive, and, unfortunately,
        # there is nothing we can do about it. This is a reported bug in asyncio.
        # https://bugs.python.org/issue39758
        connection.client.writer.close()
        await connection.client.writer.wait_closed()

        # Calls the client 'disconnected' middleware.
        for mw in self.middlewares:
            await mw.client_disconnected(connection=connection)
