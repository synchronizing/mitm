"""
Middleware for mitm.
"""

from typing import Tuple
import asyncio


class Middleware(object):
    def __init__(self, connection):
        self.connection = connection

        self.client: Tuple[asyncio.StreamReader, asyncio.StreamWriter] = (None, None)
        self.server: Tuple[asyncio.StreamReader, asyncio.StreamWriter] = (None, None)

    async def client_connected(self, reader, writer) -> None:
        """
        Called when the connection is established with the client.
        """
        self.client = (reader, writer)

    async def server_connected(self, reader, writer) -> None:
        """
        Called when the connection is established with the server.
        """
        self.server = (reader, writer)

    async def client_data(self, request: bytes) -> bytes:
        """
        Called when data is received from the client.

        Notes:
            Modifying the request will only modify the request sent to the destination
            server, and not the request mitm interprets. In other words, modifying the
            'Host' headers will not change the destination server.

            Raw TLS/SSL handshake is not sent through this method.
        """
        return request

    async def server_data(self, response: bytes) -> bytes:
        """
        Called when data is received from the server.
        """
        return response

    async def client_disconnected(self):
        """
        Called when the client disconnects.
        """

    async def server_disconnected(self):
        """
        Called when the server disconnects.
        """
