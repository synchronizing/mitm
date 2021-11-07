################
Customizing mitm
################

Middlewares
-----------

Middlewares are simple hooks that can be used to customize the behavior of ``mitm``. To initiate a middleware you need to create a class that inherits from the :py:class:`mitm.middleware.Middleware` class.

Middlewares can be used for two things:

1. As hooks for certain events that occur during the ``mitm`` flow.
2. As a way to modify incoming requests, and outgoing responses. 

For more advance customizations you will need to inherit and modify :py:class:`mitm.mitm.MITM` directly. We'll cover this later.

Example
*******

Say we wanted to create a simple middleware that logged everything that happened within our server. To do this, we would create a middleware like so:

.. code-block:: python

    from mitm import Middleware, Config, MITM
    import logging

    class MyMiddleware(Middleware):
        async def client_connected(self, reader, writer):
            await super().client_connected(reader, writer)
            logging.info("A client has connected to the mitm.")

        async def server_connected(self, reader, writer):
            await super().server_connected(reader, writer)
            logging.info("Mitm connected to the server on behalf of the client.")

        async def client_data(self, request):
            logging.info("Client send data intended to the destination server:\n\n\t%s\n" % request)
            return request

        async def server_data(self, response): 
            logging.info("The server replied to the client:\n\n\t%s\n" % response)
            return response

        async def client_disconnected(self):
            logging.info("The client has disconnected with the mitm.")

        async def server_disconnected(self):
            logging.info("The mitm has disconnected with the server.")

To use our newly created middleware we would add it to the ``mitm`` via :py:class:`mitm.config.Config`, and start our server:

.. code-block:: python
    
    from mitm import Middleware, Config, MITM
    import logging

    class MyMiddleware(Middleware):
        ...

    config = Config()
    config.add_middleware(MyMiddleware)

    mitm = MITM(config)
    mitm.start()

With our middleware in place we can send data through the ``mitm`` to see what happens.

.. code-block:: python

    import requests

    proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
    requests.get("https://api.ipify.org?format=json", proxies=proxies, verify=False)

Running the above example will output the following output on our server:

.. code-block::

    2021-11-06 22:03:34 INFO     Booting up server on 127.0.0.1:8888.
    2021-11-06 22:03:36 INFO     Client 127.0.0.1:57977 has connected.
    2021-11-06 22:03:36 INFO     A client has connected to the mitm.
    2021-11-06 22:03:36 INFO     Client send data intended to the destination server:

            b'CONNECT api.ipify.org:443 HTTP/1.0\r\n\r\n'

    2021-11-06 22:03:37 INFO     Mitm connected to the server on behalf of the client.
    2021-11-06 22:03:37 INFO     Client send data intended to the destination server:

            b'GET /?format=json HTTP/1.1\r\nHost: api.ipify.org\r\nUser-Agent: python-requests/2.26.0\r\nAccept-Encoding: gzip, deflate\r\nAccept: */*\r\nConnection: keep-alive\r\n\r\n'

    2021-11-06 22:03:37 INFO     The server replied to the client:

            b'HTTP/1.1 200 OK\r\nServer: Cowboy\r\nConnection: keep-alive\r\nContent-Type: application/json\r\nVary: Origin\r\nDate: Sun, 07 Nov 2021 02:03:37 GMT\r\nContent-Length: 21\r\nVia: 1.1 vegur\r\n\r\n{"ip":"xx.xx.xx.xx"}'

    2021-11-06 22:03:37 INFO     The mitm has disconnected with the server.
    2021-11-06 22:03:37 INFO     The client has disconnected with the mitm.
    2021-11-06 22:03:37 INFO     Successfully closed connection with 127.0.0.1:57977.

Note that the ``client_data`` and ``server_data`` methods are called for every request and response. If the client and the server are speaking back-and-forth, these methods will be called for every request and response - this includes non-HTTP protocol requests and responses. This is something to keep in mind when writting a middleware as the state of the communication will be changing, and it's up to the developer to adapt appropriately. 

----

Inheriting & Modifying ``mitm``
-------------------------------

For advance needs inheriting and modifying the :py:class:`mitm.mitm.MITM` class is the way to go. Cases like:

* Changing the destination server on the fly.
* Updating the way ``mitm`` handles the TLS/SSL handshake.
* Modifying how the ``mitm`` handles the initial request.
* Adding support for a new protocol.
* etc.

Require a more advance understanding of the ``mitm`` class. We'll cover this in more details now, starting with the flow of how the ``mitm`` class works.

Flow
****

The flow of the ``mitm`` is the way in which data is passed through the system. The flow is as follows:

1. When a client connects to the server a new ``mitm.mitm.MITM`` object is created to handle the connection. 
2. ``asyncio`` creates a new ``reader`` and ``writer`` object that is used to communicate with the client, and passes them to :py:meth:`mitm.mitm.MITM.client_connect` (you can read more on ``asyncio``'s detail `here <https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.create_server>`_).
3. :py:meth:`mitm.mitm.MITM.client_connect` stores the client's ``reader`` and ``writer`` in the ``mitm`` object and calls :py:meth:`mitm.mitm.MITM.client_request` to process the initial request.
4. :py:meth:`mitm.mitm.MITM.client_request` processes the initial request and either:
    a. Calls :py:meth:`mitm.mitm.MITM.client_tls_handshake` to initiate a TLS/SSL handshake, and *then* calls 4b (below).
    b. Calls :py:meth:`mitm.mitm.MITM.server_connect` to connect to the destination server.
5. :py:meth:`mitm.mitm.MITM.server_connect` creates a new ``reader`` and ``writer`` object that is used to communicate with the destination server. This method then calls :py:meth:`mitm.mitm.MITM.relay`, which begins the data relay between the client and the destination server.
6.  :py:meth:`mitm.mitm.MITM.relay` relays the data between the client and destination server via the :py:meth:`mitm.mitm.MITM.forward` method through some ``asyncio`` coroutines, and finally, the client and destination server disconnect once the data has been delayed.
  
Example
*******

Say we wanted to change the destination server of every connection (perhaps to a non-mitm proxy). We could do this by modifying the :py:meth:`mitm.mitm.MITM.server_connect` function. To do this we need to look into the source code for that function and see how it first works:

.. code-block:: python

    ...

    async def server_connect(self) :
        """
        Connects to destination server.
        """

        host, port = self.server_info
        reader, writer = await asyncio.open_connection(
            host=host,
            port=port,
            ssl=self.ssl,
        )
        self.server = (reader, writer)

        # Passes the server connection to middlewares.
        for middleware in self.middlewares:
            await middleware.server_connected(*self.server)

        # Relay info back an forth between the client/server.
        await self.relay()

    ...

Simply enough, the function opens a ``reader`` and ``writer`` to the destination server (which is stored in ``self.server_info``) and stores them in ``self.server``. To modify the destination server we just need to change the ``self.server_info`` varible *before calling* :py:meth:`mitm.mitm.MITM.server_connect`. To do this, we could do the following:

.. code-block:: python

    from mitm import MITM

    class MyMITM(MITM):
        async def server_connect(self):
            self.server_info = ('my.proxy.com', 80)
            super().server_connect()

    mitm = MyMITM()
    mitm.start()

and just like that, we have modified the destination server.
