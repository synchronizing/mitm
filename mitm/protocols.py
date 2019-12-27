from termcolor import colored
import asyncio
import ssl

from .stream import EmulatedClient
from .request import HTTPRequest


class HTTP(asyncio.Protocol):
    def __init__(self):
        # Starting our emulated client. This object talks with the server.
        self.emulated_client = EmulatedClient()

        # Stores the CONNECT statement if HTTPS protocol used.
        self.connect_statement = None

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        # Printing the data.
        print(colored("\nSENDING DATA:\n", "yellow"))
        print(data)

        # Starting our emulated client.
        self.reply(data)

    def ssl_connect(self, data):
        # Stores and prints the SSL CONNECT statement.
        self.connect_statement = data
        print(self.connect_statement)

    def reply(self, data):
        if self.connect_statement:
            reply = self.emulated_client.send_request(
                connect=self.connect_statement, data=data
            )
        else:
            reply = self.emulated_client.send_request(connect=None, data=data)

        # Writing back to the client.
        self.transport.write(reply)

        # Printing the reply back to console.
        print(colored("\nSERVER REPLY:\n", "yellow"))
        # print(reply, "\n")

        # Closing connection with the client.
        self.close()

    def close(self):
        self.transport.close()
        print(colored("CLOSING CONNECTION\n", "red"))


class Interceptor(asyncio.Protocol):
    def __init__(self):
        # Initiating our HTTP transport with the emulated client.
        self.HTTP_Protocol = HTTP()

        # Setting our SSL context for the HTTPS server.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain("ssl/server.crt", "ssl/server.key")

        # Opening our HTTPS transport.
        self.HTTPS_Protocol = asyncio.sslproto.SSLProtocol(
            loop=asyncio.get_running_loop(),
            app_protocol=HTTP(),
            sslcontext=ssl_context,
            waiter=None,
            server_side=True,
        )

        # Creates the TLS flag.
        self.using_tls = False

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
        request = HTTPRequest(data)
        if request.command == "CONNECT" and self.using_tls == False:
            # Replies to the client that the server has connected.
            self.transport.write(b"HTTP/1.1 200 OK\r\n\r\n")
            # Does a TLS/SSL handshake with the client.
            self.HTTPS_Protocol.connection_made(self.transport)
            # Sets our TLS flag to true.
            self.using_tls = True

            # Sends the CONNECT to the HTTPS_Protocol protocol for storage and print.
            # Since this is the initial 'CONNECT' data, it will be unencrypted.
            self.HTTPS_Protocol._app_protocol.ssl_connect(data)
        elif self.using_tls:
            # With HTTPS protocol enabled, receives encrypted data from the client.
            self.HTTPS_Protocol.data_received(data)
        else:
            # Receives standard, non-encrypted data from the client (TLS/SSL is off).
            self.HTTP_Protocol.connection_made(self.transport)
            self.HTTP_Protocol.data_received(data)
