"""
Middleware base class for mitm.
"""

import asyncio
from typing import Tuple

from . import mitm


class Middleware:
    def __init__(self, connection: "mitm.MITM"):
        """
        Initialize the middleware.
        """

        self.connection = connection

        self.client: Tuple[asyncio.StreamReader, asyncio.StreamWriter] = (None, None)
        self.server: Tuple[asyncio.StreamReader, asyncio.StreamWriter] = (None, None)

    async def client_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) :
        """
        Called when the connection is established with the client.

        Args:
            reader: The reader for the client.
            writer: The writer for the client.
        """
        self.client = (reader, writer)

    async def server_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) :
        """
        Called when the connection is established with the server.

        Args:
            reader: The reader for the server.
            writer: The writer for the server.
        """
        self.server = (reader, writer)

    async def client_data(self, request: bytes) -> bytes:
        """
        Called when data is received from the client.

        Note:
            Modifying the request will only modify the request sent to the destination
            server, and not the request mitm interprets. In other words, modifying the
            'Host' headers will not change the destination server.

            Raw TLS/SSL handshake is not sent through this method.

        Args:
            request: The request received from the client.

        Returns:
            The request to send to the server.
        """
        return request

    async def server_data(self, response: bytes) -> bytes:
        """
        Called when data is received from the server.

        Args:
            response: The response received from the server.

        Returns:
            The response to send back to the client.
        """
        return response

    async def client_disconnected(self):
        """
        Called when the client disconnects.

        Note:
            By the time this method is called, the client will have already successfully
            disconnected.
        """

    async def server_disconnected(self):
        """
        Called when the server disconnects.

        Note:
            By the time this method is called, the server will have already successfully
            disconnected.
        """
