from .gen_keys import create_self_signed_cert

from http_parser.parser import HttpParser
import asyncio
import ssl

from termcolor import colored


class HTTP(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        # Prints the data the client has sent.
        print(data)

        # Writes back the client.
        self.transport.write(b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n")
        self.transport.write(b"This seems to be working. Replying from HTTP.")

        # Closest the connection with the client, and prints info.
        self.transport.close()
        print(colored("CLOSING CONNECTION\n", "red"))

    def close(self):
        self.transport.close()


class Interceptor(asyncio.Protocol):
    def __init__(self):
        # Loading the protocol certificates.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain("ssl/server.crt", "ssl/server.key")

        # Initiates the HttpParser object.
        self.http_parser = HttpParser()

        # Creates the TLS flag.
        self.using_tls = False

        # Initiating our HTTP transport.
        self.HTTP_Protocol = HTTP()

        # Setting our SSL context for the server.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain("ssl/server.crt", "ssl/server.key")

        # Opening our HTTPS transport.
        self.HTTPS_Protocol = asyncio.sslproto.SSLProtocol(
            loop=asyncio.get_running_loop(),
            app_protocol=self.HTTP_Protocol,
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


class ManInTheMiddle(object):
    def __init__(self, host="127.0.0.1", port=8080, gen_ssl=True):
        # Generates self-signed SSL certificates.
        if gen_ssl:
            create_self_signed_cert()

        self.loop = None

    async def start(self):
        # Gets the current event loop (or creates one).
        self.loop = asyncio.get_event_loop()

        # Creates the server instance.
        self.server = await self.loop.create_server(
            Interceptor, host="127.0.0.1", port=8888
        )

        # Prints information about the server.
        ip, port = self.server.sockets[0].getsockname()
        print(colored("Routing traffic on server {}:{}.\n".format(ip, port), "green"))

        # Starts the server instance.
        await self.server.serve_forever()
