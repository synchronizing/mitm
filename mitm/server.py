""" Man in the middle server module.

The objects below are the primary interface between the client and the mitm
server. Interceptor, HTTP, and HTTPS objects are defined as 'asyncio.Protocol'
objects.

MITM works in the following steps:

    1. Client request is intercepted by the Interceptor protocol.

    2. The Interceptor decides whether the client request is a HTTP or HTTPS,
    sending it to the correct protocol (via the transporter object).

    3. The HTTP/HTTPS protocol receives the clients data, and creates an
    EmulatedClient to send the information to the designated server.

    4. The HTTP/HTTPS protocol then replies back to the client via the
    transporter object.

To understand this module it's recommended to read the documentation in the
following order:

    1. Interceptor
    2. HTTP
    3. HTTPS
"""

import asyncio
import ssl

from .client import EmulatedClient
from .utils import HTTPRequest, color


class HTTP(asyncio.Protocol):
    """ Protocol for speaking with client via HTTP.

    This class overrides the methods described by the asyncio.Protocol class.  

    Args:
        emulated_client (EmulatedClient): Emulated client that speakes to outbound server.
        transport (asyncio.BaseTransport): Transporter that read/writes to client.
        connect_statement (bytes):  The HTTP CONNECT method message.
    """

    def __init__(self):
        # Starting our emulated client. This object talks with the server.
        self.emulated_client = EmulatedClient()

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        # Creates emulated client.
        emulated_client = EmulatedClient()

        # Printing prompt.
        print(color.yellow("\nSENDING DATA:\n"))

        # Checks if we are in the HTTP or HTTPS class.
        if "connect_statement" in self.__dict__:
            emulated_client.sock_connect_tls(self.connect_statement)

            # Prints the connect statement.
            print(self.connect_statement, "\n")
        else:
            emulated_client.sock_connect(data)

        # Prints the data.
        print(data)

        # Sends the data to the server.
        emulated_client.sock_send(data)

        # Recives the reply and responds back to client.
        reply = emulated_client.sock_receive()
        self.transport.write(reply)

        # Closing the EmulatedClient socket.
        emulated_client.sock_close()

        # Printing the reply back to console.
        print(color.yellow("\nSERVER REPLY:\n"))
        print(reply)

        # Closing connection with the client.
        self.close()

    def close(self):
        print(color.red("\nCLOSING CONNECTION\n"))

        # Closes connection with the client.
        self.transport.close()


class HTTPS:
    """ Protocol for speaking with client via HTTPS.

    This is an abstract class that upgrades the HTTP protocol to support SSL.
    On invoking this class, the __new__ method returns an upgraded version of
    the HTTP() object above.

    """

    def __new__(cls, rsa):
        """ Initializes the HTTPS proctol.

        Note:
            asyncio.sslproto.SSLProtocol is part of asyncio's private API and is
            not officially documented. Reference to the code can be found in the
            cpython implementation of SSLProtocol:

            https://github.com/python/cpython/blob/5cd28030092eaa8eb9223afd733974fd2afc8e2c/Lib/asyncio/sslproto.py#L404-L734

        Args:
            rsa (RSA): Object containing a RSA certificate and private key.
        """

        # Setting our SSL context for the HTTPS server.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        ssl_context.load_cert_chain(rsa.certificate_file, rsa.private_key_file)

        # Returning our HTTPS transport.
        return asyncio.sslproto.SSLProtocol(
            loop=asyncio.get_running_loop(),
            app_protocol=HTTP(),
            sslcontext=ssl_context,
            waiter=None,
            server_side=True,
        )


class Interceptor(asyncio.Protocol):
    """ Protocol that intercepts the clients request.

    The Interceptor class is the middle-man that intercepts the clients out-bound
    requests. When a client sends a request to an outbound server (say google.com),
    the Interceptor will intercept the clients connection and create an
    asyncio.Transporter to communicate back and forth with the client. After
    connecting with the client the Interceptor will interpret the client's request
    and send it either to the HTTP or HTTPS protocol (depending if the clients
    request contains the HTTP CONNECT method or not).

    Notes:
        Protocols:
            https://docs.python.org/3.5/library/asyncio-protocol.html#protocols

        Transports:
            https://docs.python.org/3.5/library/asyncio-protocol.html#transports

        HTTP CONNECT:
            https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods/CONNECT

    Attributes:
        HTTP (HTTP): Protocol for communicating with client via HTTP.
        HTTPS (HTTPS): Protocol for communicating with client via HTTPS.
        using_tls (bool): Flag to designate if the client is using TLS/SSL.
        transport (asyncio.BaseTransport): Transporter that communicates with the client.
    """

    def __init__(self, rsa):
        """ Initializes the Interceptor class.

        Args:
            rsa (RSA): Object containing a RSA certificate and private key.
        """
        # Initiating our HTTP/HTTPS protocols.
        self.HTTP = HTTP()
        self.HTTPS = HTTPS(rsa)

        # Creates the TLS flag. Will be used later.
        self.using_tls = False

    def connection_made(self, transport):
        """ Called when client makes initial connection to the server. """

        # Setting our transport object.
        self.transport = transport

        # Getting the client address and port number.
        address, port = self.transport.get_extra_info("peername")

        # Prints opening client information.
        print(color.blue(f"CONNECTING WITH {address}:{port}"))

    def data_received(self, data):
        """ Called when a connected client sends data to the server.

        This method is called only once during a standard HTTP connection with
        the client. If the client is using HTTPS (SSL/TLS) this method is called
        twice. In the first step, the client sends the server a message to connect;
        HTTP "CONNECT". The server follows up by replying with "OK" and begins
        the TLS handshake with the client. After the handshake is done, the client
        sends to the server the encrypted HTTP requests; "GET", "POST", etc.
        """

        # Parses the data the client has sent to the server.
        request = HTTPRequest(data)

        # Decides where to send data to (HTTP or HTTPS protocol).
        if request.command == "CONNECT" and self.using_tls == False:

            # Replies to the client that the server has connected.
            self.transport.write(b"HTTP/1.1 200 OK\r\n\r\n")

            # Does a TLS/SSL handshake with the client.
            self.HTTPS.connection_made(self.transport)

            # Sets our TLS flag to true.
            self.using_tls = True

            # Sends the CONNECT to the HTTPS protocol for storage and print.
            # Since this is the initial 'CONNECT' data, it will be unencrypted.
            self.HTTPS._app_protocol.connect_statement = data

        elif self.using_tls:

            # With HTTPS protocol enabled, receives encrypted data from the client.
            self.HTTPS.data_received(data)

        else:
            # Receives standard, non-encrypted data from the client (TLS/SSL is off).
            self.HTTP.connection_made(self.transport)
            self.HTTP.data_received(data)
