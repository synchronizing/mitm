from .gen_keys import create_self_signed_cert
from .protocols import Interceptor

import asyncio
from termcolor import colored


class ManInTheMiddle(object):
    """ Class for initializing the ManInTheMiddle attack. """

    def __init__(self, host="127.0.0.1", port=8888, gen_ssl=True):
        # Generates self-signed SSL certificates.
        if gen_ssl:
            create_self_signed_cert()

        self.host = host
        self.port = port

    async def start(self):
        # Gets the current event loop (or creates one).
        self.loop = asyncio.get_event_loop()

        # Creates the server instance.
        self.server = await self.loop.create_server(
            Interceptor, host=self.host, port=self.port
        )

        # Prints information about the server.
        ip, port = self.server.sockets[0].getsockname()
        print(colored("Routing traffic on server {}:{}.\n".format(ip, port), "green"))

        # Starts the server instance.
        await self.server.serve_forever()
