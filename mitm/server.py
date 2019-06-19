from mitm.gen_keys import create_self_signed_cert

from http_parser.parser import HttpParser
from termcolor import colored
import asyncio
import ssl
import os


class Http(asyncio.Protocol):
    def __init__(self, data):
        super().__init__()

        self.data = data

        # Creates our HttpParser object.
        self.http_parser = HttpParser()

        # Creates the placeholder for the transport.
        self.transport = None

        # Placeholder for client information.
        self.client_addr = None
        self.client_ip = None

    def connection_made(self, transport):
        self.transport = transport

        # Saves info about client.
        self.client_addr, self.client_ip = self.transport.get_extra_info("peername")

    def request_received(self):
        self.transport.write(
            b"HTTP/1.1 200 OK\r\n" + b"Connection: close\r\n\r\n" + self.data
        )
        self.close()

    def data_received(self, data):
        # Prints the data the client has sent.
        print(data.decode())

        # HTTP Parser reads the clients data and stores results in different methods.
        self.http_parser.execute(data, len(data))
        if self.http_parser.is_message_complete():
            self.request_received()

    def close(self):
        # Prints closing client information.
        print(colored(f"CLOSING {self.client_addr}:{self.client_ip}\n", "red"))

        self.transport.close()


class Https(Http):
    def __init__(self, data):
        super().__init__(data)

        # Loading the protocol certificates.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain("ssl/server.crt", "ssl/server.key")

        # Opening our SSL transport.
        self.transport_ssl = asyncio.sslproto.SSLProtocol(
            loop=asyncio.get_running_loop(),
            app_protocol=Http(self.data),
            sslcontext=ssl_context,
            waiter=None,
            server_side=True,
        )

        # Client information.
        self.client_method = False

    def connection_made(self, transport):
        super().connection_made(transport)

        # Prints opening client information.
        print(colored(f"OPENED {self.client_addr}:{self.client_ip}\n\n", "blue"))

    def request_received(self):
        self.client_method = self.http_parser.get_method()
        if self.client_method == "CONNECT":
            # Replies to client that the HTTPS server has connected.
            self.transport.write(b"HTTP/1.1 200 OK\r\n\r\n")
            # Creates the SSL handshake.
            self.transport_ssl.connection_made(self.transport)
        else:
            super().request_received()

    def data_received(self, data):
        if self.client_method == "CONNECT":
            # Receives data via the HTTPS protocol.
            self.transport_ssl.data_received(data)
        else:
            # Receives data via the HTTP protocol.
            super().data_received(data)


class ManInTheMiddle(object):
    def __init__(self, data, addr="127.0.0.1", port=8888):
        self.data = data
        self.addr, self.port = addr, port
        self.generate_keys()

    def generate_keys(self):
        if not os.path.exists("ssl"):
            os.makedirs("ssl")

        create_self_signed_cert()

    async def start_server(self):
        # Get event loop.
        self.loop = asyncio.get_event_loop()

        # Starts the server.
        server = await self.loop.create_server(
            lambda: Https(self.data), host=self.addr, port=self.port
        )

        # Prints information about the server.
        ip, port = server.sockets[0].getsockname()
        print(colored("Routing traffic on server {}:{}.\n".format(ip, port), "green"))

        # Starts the server.
        await server.serve_forever()
