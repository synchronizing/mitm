from .stream import EmulatedClient

from termcolor import colored
from http_parser.parser import HttpParser
import asyncio
import ssl


class HTTP(asyncio.Protocol):
    def __init__(self, using_ssl):
        # Starting our emulated client. This object talks with the server.
        self.emulated_client = EmulatedClient(using_ssl=using_ssl)

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        # Printing the data.
        print(colored("\nSENDING DATA:\n", "yellow"))
        print(data)

        # Starting our emulated client.
        loop = asyncio.get_event_loop()
        loop.create_task(self.reply(data))

    async def reply(self, data):
        # Gathering the reply from the emulated client.
        reply = await self.emulated_client.connect(data)

        # Writing back to the client.
        self.transport.write(reply)

        # Printing the reply back to console.
        print(colored("\nSERVER REPLY:\n", "yellow"))
        print(reply, "\n")

        # Closing connection with the client.
        self.close()

    def close(self):
        self.transport.close()
        print(colored("CLOSING CONNECTION\n", "red"))


class Interceptor(asyncio.Protocol):
    def __init__(self):
        # Loading the protocol certificates.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain("ssl/server.crt", "ssl/server.key")

        # Initiates the HttpParser object.
        self.http_parser = HttpParser()

        # Creates the TLS flag.
        self.using_tls = False

        # Initiating our HTTP transport with the emulated client.
        self.HTTP_Protocol = HTTP(using_ssl=False)

        # Setting our SSL context for the server.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain("ssl/server.crt", "ssl/server.key")

        # Opening our HTTPS transport.
        self.HTTPS_Protocol = asyncio.sslproto.SSLProtocol(
            loop=asyncio.get_running_loop(),
            app_protocol=HTTP(using_ssl=True),
            sslcontext=ssl_context,
            waiter=None,
            server_side=True,
        )

    def connection_made(self, transport):
        """ Called when client makes initial connection to the server. Receives a transporting object from the client. """

        # Setting our transport object.
        self.transport = transport

        # Getting the client address and port number.
        self.client_addr, self.client_ip = self.transport.get_extra_info("peername")

        # Prints opening client information.
        print(colored(f"CONNECTING WITH {self.client_addr}:{self.client_ip}", "blue"))

    def data_received(self, data):
        """
            Called when a connected client sends data to the server; HTTP or HTTPS requests.

            Note:
                This method is called multiple times during a typical TLS/SSL connection with a client.
                    1. Client sends server message to connect; "CONNECT."
                    2. Server replies with "OK" and begins handshake.
                    3. Client sends server encrypted HTTP requests; "GET", "POST", etc.
        """

        # Parses the data the client has sent to the server.
        self.http_parser.execute(data, len(data))

        if self.http_parser.get_method() == "CONNECT" and self.using_tls == False:
            # Replies to the client that the server has connected.
            self.transport.write(b"HTTP/1.1 200 OK\r\n\r\n")
            # Does a TLS/SSL handshake with the client.
            self.HTTPS_Protocol.connection_made(self.transport)
            # Sets our TLS flag to true.
            self.using_tls = True

            # Prints the data the client has sent. Since this is the initial 'CONNECT' data, it will be unencrypted.
            print(data)
        elif self.using_tls:
            # With HTTPS protocol enabled, receives encrypted data from the client.
            self.HTTPS_Protocol.data_received(data)
        else:
            # Receives standard, non-encrypted data from the client (TLS/SSL is off).
            self.HTTP_Protocol.connection_made(self.transport)
            self.HTTP_Protocol.data_received(data)
