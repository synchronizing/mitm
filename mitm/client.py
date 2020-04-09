""" Man in the middle emulated client module.

To accomplish a proper man-in-the-middle attack with TLS capability
the mitm server must be the one sending the original request to the outbound
server. With the emulated client we are changing the typical structure:

    client <-> server

To one that looks like so:

    client <-> mitm (server) <-> mitm (emulated client) <-> server

Where we then reply back to the client with the response the emulated client
retrieved from the server on behalf of the client. This module defines the
mitm (emulated client) portion.
"""

import socket
import ssl

from .utils import HTTPRequest


class EmulatedClient(object):
    """ Class for emulating the client to the server.

    Attributes:
        sock (socket.socket): Socket to communicate with outbound server.
        server_address: The address of the outbound server.
    """

    def __init__(self, timeout=3):
        """ Initializes the emulated client.

        Args:
            timeout (int): How long the socket should wait before timing-out.
        """

        socket.setdefaulttimeout(timeout)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def sock_connect(self, data):
        """ Connects socket with the outbound server.

        Args:
            data (bytes): HTTP request (GET, POST, etc.)
        """

        self.server_address = (HTTPRequest(data).headers["HOST"], 80)
        self.sock.connect(self.server_address)

    def sock_connect_tls(self, connect):
        """ Connects socket with the oubound server using HTTPS.

        Args:
            connect (bytes): CONNECT HTTP request.
        """

        path = HTTPRequest(connect).path.split(":")
        self.sever_address = (path[0], int(path[1]))

        self.sock.connect(self.sever_address)
        self.sock = ssl.wrap_socket(
            self.sock,
            keyfile=None,
            certfile=None,
            server_side=False,
            cert_reqs=ssl.CERT_NONE,
            ssl_version=ssl.PROTOCOL_SSLv23,
        )

    def sock_send(self, data):
        """ Sends data through the socket.

        Args:
            data (bytes): HTTP request.
        """

        self.sock.send(data)

    def sock_receive(self):
        """ Receives data through the socket. """

        response = b""

        while True:
            try:
                buf = self.sock.recv(1024)
                if not buf:
                    break
                else:
                    response += buf
            except Exception as e:
                break

        return response

    def sock_close(self):
        """ Closes the socket. """

        self.sock.close()
