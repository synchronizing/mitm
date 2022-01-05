"""
Custom middlware implementation for the MITM proxy.
"""

from abc import ABC, abstractstaticmethod

from .core import Connection


class Middleware(ABC):
    @abstractstaticmethod
    async def mitm_started(host: str, port: int):
        """
        Called when the mitm has started.
        """
        raise NotImplementedError

    @abstractstaticmethod
    async def client_connected(connection: Connection):
        """
        Called when the connection is established with the client.
        """
        raise NotImplementedError

    @abstractstaticmethod
    async def server_connected(connection: Connection):
        """
        Called when the connection is established with the server.
        """
        raise NotImplementedError

    @abstractstaticmethod
    async def client_data(connection: Connection, data: bytes) -> bytes:
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

    @abstractstaticmethod
    async def server_data(connection: Connection, data: bytes) -> bytes:
        """
        Called when data is received from the server.

        Args:
            response: The response received from the server.

        Returns:
            The response to send back to the client.
        """
        raise NotImplementedError

    @abstractstaticmethod
    async def client_disconnected(connection: Connection):
        """
        Called when the client disconnects.
        """
        raise NotImplementedError

    @abstractstaticmethod
    async def server_disconnected(connection: Connection):
        """
        Called when the server disconnects.

        Note:
            By the time this method is called, the server will have already successfully
            disconnected.
        """
        raise NotImplementedError


import logging

logger = logging.getLogger(__package__)


class Log(Middleware):
    """
    Logging middleware.
    """
    @staticmethod
    async def mitm_started(host: str, port: int):
        logger.info("MITM started on %s:%d." % (host, port))

    @staticmethod
    async def client_connected(connection: Connection):
        host, port = connection.client.writer._transport.get_extra_info("peername")
        logger.info("Client %s:%i has connected." % (host, port))

    @staticmethod
    async def server_connected(connection: Connection):
        host, port = connection.server.writer._transport.get_extra_info("peername")
        logger.info("Connected to server %s:%i." % (host, port))

    @staticmethod
    async def client_data(connection: Connection, data: bytes) -> bytes:
        logger.info("Client to server: \n\n\t%s\n" % data)
        return data

    @staticmethod
    async def server_data(connection: Connection, data: bytes) -> bytes:
        logger.info("Server to client: \n\n\t%s\n" % data)
        return data

    @staticmethod
    async def client_disconnected(connection: Connection):
        logger.info("Client has disconnected.")

    @staticmethod
    async def server_disconnected(connection: Connection):
        logger.info("Server has disconnected.")
