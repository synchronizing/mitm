"""
Custom middlware implementation for the MITM proxy.
"""

from abc import ABC, abstractmethod

from .core import Connection


class Middleware(ABC):
    @abstractmethod
    async def mitm_started(self, host: str, port: int):
        """
        Called when the mitm has started.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_connected(self, connection: Connection):
        """
        Called when the connection is established with the client.
        """
        raise NotImplementedError

    @abstractmethod
    async def server_connected(self, connection: Connection):
        """
        Called when the connection is established with the server.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_data(self, connection: Connection, data: bytes) -> bytes:
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
        raise NotImplementedError

    @abstractmethod
    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        """
        Called when data is received from the server.

        Args:
            response: The response received from the server.

        Returns:
            The response to send back to the client.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_disconnected(self, connection: Connection):
        """
        Called when the client disconnects.
        """
        raise NotImplementedError

    @abstractmethod
    async def server_disconnected(self, connection: Connection):
        """
        Called when the server disconnects.

        Note:
            By the time this method is called, the server will have already successfully
            disconnected.
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<Middleware: {self.__class__.__name__}>"


import logging

logger = logging.getLogger(__package__)


class Log(Middleware):
    """
    Logging middleware.
    """

    def __init__(self):
        self.connection: Connection = None

    async def mitm_started(self, host: str, port: int):
        logger.info("MITM server started on %s:%d." % (host, port))

    async def client_connected(self, connection: Connection):
        logger.info("Client %s has connected." % (connection.client))

    async def server_connected(self, connection: Connection):
        logger.info("Connected to server %s." % (connection.server))

    async def client_data(self, connection: Connection, data: bytes) -> bytes:

        # The first request is intended for the 'mitm' server to discover the
        # destination server.
        if not connection.server:
            logger.info("Client %s to mitm: \n\n\t%s\n" % (connection.client, data))

        # All requests thereafter are intended for the destination server.
        else:
            logger.info("Client %s to server %s: \n\n\t%s\n" % (connection.client, connection.server, data))

        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        logger.info("Server %s to client %s: \n\n\t%s\n" % (connection.server, connection.client, data))
        return data

    async def client_disconnected(self, connection: Connection):
        logger.info("Client %s has disconnected." % (connection.client))

    async def server_disconnected(self, connection: Connection):
        logger.info("Server %s has disconnected." % (connection.server))
