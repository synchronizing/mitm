########################
Custom `mitm.Middleware`
########################

Understanding and overview of a custom middleware. 

----

Middlewares are simple hooks that are called in different stages of the client connection, and can be used to modify incoming and outgoing requests. To initiate a middleware you need to create a class that inherits from the `mitm.middleware.Middleware` class. Middlewares can be used for two things:

1. As hooks for certain events that occur during the `mitm` flow.

2. As a way to modify incoming requests, and outgoing responses.

Middlewares can implement the following methods:

.. class:: mitm.Middleware

    .. method:: mitm_started(host: str, port: int)
        :async:
        :staticmethod:

        Called when the `mitm` server boots-up.

    .. method:: client_connected(connection: Connection)
        :async:
        :staticmethod:

        Called when a client connects to the `mitm` server. Note that the `mitm.core.Connection` object is not fully initialized yet, and only contains a valid client `mitm.core.Host`.

    .. method:: server_connected(connection: Connection)
        :async:
        :staticmethod:

        Called when the `mitm` connects with the destination server. At this point the `mitm.core.Connection` object is fully initialized.

    .. method:: client_data(connection: Connection, data: bytes)
        :async:
        :staticmethod:

        Called when the `mitm` receives data from the client. The first incoming data is the HTTP request that is passed through the `mitm.protocol.Protocol`'s to resolve the destination server and it cannot be modified. Data that comes through this hook can be modified and returned to the `mitm` as new data to be sent to the destination server.

        Note:
            This method **must** return back data. Modified or not.

    .. method:: server_data(connection: Connection, data: bytes)
        :async:
        :staticmethod:

        Called when the `mitm` receives data from the destination server. Data that comes through this hook can be modified and returned to the `mitm` as new data to be sent to the client.

        Note:
            This method **must** return back data. Modified or not.  

    .. method:: client_disconnected(connection: Connection)
        :async:
        :staticmethod:

        Called when the `mitm` disconnects from the client.

    .. method:: server_disconnected(connection: Connection)
        :async:
        :staticmethod:

        Called when the `mitm` disconnects from the destination server.

An example of a middleware is the built-in `mitm.middleware.Log` middleware, which looks like so:

.. code-block:: python

    from mitm import Middleware, Connection

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
