"""
Custom middlware implementation for the MITM proxy.
"""

import logging

from mitm.core import Connection, Middleware
from toolbox.string.color import bold

logger = logging.getLogger(__package__)


class Log(Middleware):
    """
    Logging middleware.
    """

    def __init__(self):
        self.connection: Connection = None

    async def mitm_started(self, host: str, port: int):
        logger.info(f"MITM server started on {bold(f'{host}:{port}')}.")

    async def client_connected(self, connection: Connection):
        logger.info(f"Client {bold(connection.client)} has connected.")

    async def server_connected(self, connection: Connection):
        logger.info(f"Client {bold(connection.client)} has connected to server {bold(connection.server)}.")

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
