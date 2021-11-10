""" 
Man-in-the-middle.
"""

import asyncio
import logging
import ssl
from enum import Enum
from typing import Optional, Tuple

import httpq

from .config import Config

logger = logging.getLogger(__name__)
asyncio.log.logger.setLevel(logging.ERROR)


class Flow(Enum):
    """Enumeration of the possible flows.

    Two flows are possible: ``CLIENT_TO_SERVER`` and ``SERVER_TO_CLIENT``.
    """

    CLIENT_TO_SERVER = 0
    SERVER_TO_CLIENT = 1


class MITM:
    """
    Man-in-the-middle server.

    Note:
        In the context of this class ``client`` is the client connected to mitm, and
        ``server`` is the destination server the client is trying to connect to.
    """

    def __init__(self, config: Config = Config()):
        """
        Initializes the MITM class.

        Args:
            config: The configuration object.
        """

        # User configuration.
        self.config = config

        # Client reader, writer, IP, and port.
        self.client: Tuple[asyncio.StreamReader, asyncio.StreamWriter] = (None, None)
        self.client_info: Tuple[str, int] = (None, None)

        # Server reader, writer, IP, and port.
        self.server: Tuple[asyncio.StreamReader, asyncio.StreamWriter] = (None, None)
        self.server_info: Tuple[str, int] = (None, None)

        # Whether or not the client is using TLS/SSL.
        self.ssl: bool = False

        # First non-CONNECT request sent from client.
        self.request: Optional[httpq.Request] = None

        self.middlewares = []
        for Middleware in config.middlewares:
            self.middlewares.append(Middleware(self))

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

    async def client_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        """
        Called when a client connects to the MITM server.

        Args:
            reader: The reader of the client connection.
            writer: The writer of the client connection.
        """

        self.client = (reader, writer)
        ip, port = writer._transport.get_extra_info("peername")
        self.client_info = (ip, port)
        logger.info("Client %s:%i has connected." % self.client_info)

        # Passes the client connection to middlewares.
        for middleware in self.middlewares:
            await middleware.client_connected(*self.client)

        await self.client_request()

    async def client_request(self):
        """
        Process the client's initial request after the client has connected.
        """

        reader, _ = self.client

        # Read request from client until body.
        req = httpq.Request()
        while req.step_state() != httpq.state.BODY:
            data = await reader.read(self.config.buffer_size)
            req.feed(data)
        self.request = req

        # If the request is a CONNECT request we upgrade the connection to TLS/SSL.
        if req.method == "CONNECT":
            await self.client_tls_handshake()
            self.ssl = True

            # Resets the stored request to not relay 'CONNECT' to the server.
            self.request = b""

            # Figure out the destination server.
            host, port = req.target.string.split(":")
            self.server_info = (host, int(port))

        # If request is not a CONNECT, we use the 'Host' headers for destination server.
        else:
            self.server_info = (req.headers.get("Host").string, 80)

        # Open connection with the destination server.
        await self.server_connect()

    async def client_tls_handshake(self):
        """
        Upgrades the client connection to TLS/SSL.
        """

        reader, writer = self.client

        # Tell client to start TLS.
        writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
        await writer.drain()

        # Upgrade connection to TLS.
        transport = writer.transport
        protocol = transport.get_protocol()

        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain(self.config.rsa_cert, self.config.rsa_key)

        new_transport = await asyncio.get_event_loop().start_tls(
            transport,
            protocol,
            ssl_context,
            server_side=True,
        )

        # Replace stream with new transport.
        reader._transport = new_transport
        writer._transport = new_transport
        self.client = (reader, writer)

        logger.debug("Successfully upgraded server connection to TLS/SSL.")

    async def client_disconnect(self):
        """
        Called when the client disconnects.
        """

        logger.info("Closing connection with client %s:%i." % self.client_info)
        _, writer = self.client
        writer.close()
        await writer.wait_closed()

        # Calls the client disconnected method in middlewares.
        for middleware in self.middlewares:
            await middleware.client_disconnected()

    async def server_connect(self):
        """
        Connects to destination server.
        """

        host, port = self.server_info
        reader, writer = await asyncio.open_connection(
            host=host,
            port=port,
            ssl=self.ssl,
        )
        self.server = (reader, writer)

        # Passes the server connection to middlewares.
        for middleware in self.middlewares:
            await middleware.server_connected(*self.server)

        # Relay info back an forth between the client/server.
        await self.relay()

    async def relay(self):
        """
        Relays data between the client and destination server.
        """

        c_reader, c_writer = self.client
        s_reader, s_writer = self.server

        # Relays initial request to the server if it's not SSL. The reason why we don't
        # relay a CONNECT is because 'server_connect' does that for us.
        if not self.ssl:
            s_writer.write(self.request.raw)
            await s_writer.drain()
            logger.debug("Relayed messaged: \n\n\t%s\n\n" % self.request.raw)

        # Relay the requests between the client/server - observing them in between.
        event = asyncio.Event()
        await asyncio.gather(
            self.forward(c_reader, s_writer, event, Flow.CLIENT_TO_SERVER),
            self.forward(s_reader, c_writer, event, Flow.SERVER_TO_CLIENT),
        )

        logger.info("Successfully closed connection with %s:%i." % self.client_info)

    async def forward(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        event: asyncio.Event,
        flow: Flow,
    ):
        """
        Forwards data between a reader/writer.

        Args:
            reader: The reader of the source.
            writer: The writer of the destination.
            event: The event to wait on.
            flow: The flow of the data.
        """

        while not event.is_set():
            data = await reader.read(self.config.buffer_size)
            if data == b"":
                break
            else:

                # Runs data through middleware.
                if flow == Flow.SERVER_TO_CLIENT:
                    for middleware in self.middlewares:
                        data = await middleware.server_data(data)
                elif flow == Flow.CLIENT_TO_SERVER:
                    for middleware in self.middlewares:
                        data = await middleware.client_data(data)

                writer.write(data)
                await writer.drain()

                logger.debug("Relayed messaged: \n\n\t%s\n\n" % data)

        writer.close()
        await writer.wait_closed()

        # Calls the disconnected methods in middlewares.
        if flow == Flow.SERVER_TO_CLIENT:
            for middleware in self.middlewares:
                await middleware.server_disconnected()
        elif flow == Flow.CLIENT_TO_SERVER:
            for middleware in self.middlewares:
                await middleware.client_disconnected()
