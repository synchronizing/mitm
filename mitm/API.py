""" Man in the middle API module.

This module is intended to make it easy to start an mitm server.
"""

import asyncio

from .utils import RSA, color
from .server import Interceptor


class ManInTheMiddle(object):
    """ Class for initializing the ManInTheMiddle attack.

    Attributes:
        host (str): Host's IP.
        port (int): Host's port.
        loop (asyncio.loop): Current asyncio loop.
        server (asyncio.Server): Mitm server.
    """

    def __init__(self, host="127.0.0.1", port=8888):
        """ Initializes the mitm object.

        Args:
            host (str): Host's IP.
            port (int): Host's port.
        """
        self.host = host
        self.port = port

    def run(self):
        """ Starts the server synchronously. """

        asyncio.run(self.start())

    async def start(self):
        """ Starts the server asynchronously. """

        # Gets the current event loop (or creates one).
        self.loop = asyncio.get_event_loop()

        # Creates RSA key pair.
        self.rsa = RSA()

        # Creates the server instance.
        self.server = await self.loop.create_server(
            lambda: Interceptor(self.rsa), host=self.host, port=self.port
        )

        # Prints information about the server.
        ip, port = self.server.sockets[0].getsockname()
        print(color.green("Routing traffic on server {}:{}.\n".format(ip, port)))

        # Starts the server instance.
        await self.server.serve_forever()
