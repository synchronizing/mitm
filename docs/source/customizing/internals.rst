###################
Internals of `mitm`
###################

Quick guide on the internal structure of `mitm`.

Make sure to check out the documentation for `asyncio streams <https://docs.python.org/3/library/asyncio-stream.html>`_ before reading this section.

----

Core
****

There are two (simple) core items that `mitm` is built around:

.. class:: mitm.core.Host

    A host is a representation of a remote host - another computer on the internet that `mitm` is connected to. It contains a `asyncio.StreamReader` and `asyncio.StreamWriter` object that are used to communicate with the remote host.

    The `Host` class is a simple `dataclass <https://docs.python.org/3/library/dataclasses.html>`_ that encapsulates a single connection. It looks like so:

    .. code-block:: python

        @dataclass
        class Host:
            reader: Optional[asyncio.StreamReader] = None
            writer: Optional[asyncio.StreamWriter] = None

.. class:: mitm.core.Connection

    A connection is a representation of a connection between two hosts. More specifically, the client host, and the server host (destination server in which the client is trying to communicate to). It contains a `Host` object for the client, and a `Host` object for the server. 

    A connection also contains an `ssl_context` object which is used to create an SSL connection between the client and the `mitm` if needed. 

    The `Connection` class, like the `Host` class above, is a simple `dataclass <https://docs.python.org/3/library/dataclasses.html>`_ class. It looks like so:

    .. code-block:: python

        @dataclass
        class Connection:
            client: Host
            server: Host
            ssl_context: ssl.SSLContext

The two classes above, which are described in more details within `mitm.core`, are the core items that `mitm` is built around.

----

`mitm` server
*************

The `mitm` server boots-up a `asyncio.Server` object that listens for incoming connections. On start it creates a `Connection` object with only the client `Host` resolved, and passes it to the `mitm` function in `mitm.mitm.MITM`. The start function looks like so:

.. code-block:: python
    
    server = await asyncio.start_server(
        lambda reader, writer: self.mitm(
            Connection(
                client=Host(reader=reader, writer=writer),
                server=Host(),
                ssl_context=self.ssl_context,
            )
        ),
        host=self.host,
        port=self.port,
    )   

From there, the following steps occur:

1. The `mitm.middleware.Middleware.client_connected` function is called for all middlewares.

2. The minimum bytes needed to identify which protocol is being used is read from the client connection.

3. The `mitm.middleware.Middleware.client_data` function is called for all middlewares.

4. The data is cycled through all protocols via `mitm.protocol.Protocol.connect` until one protocol returns `True` to indicate it has successfully resolved, and connected to the host.

5. Two possible outcomes can happen here:

   - If the no protocol was successful the connection is closed with the client, and the `mitm.middleware.Middleware.client_disconnected` function is called for all middlewares.

   - If connection to the destination server was successful, then the `mitm.middleware.Middleware.server_connected` function is called for all middlewares.

6. If the server connected successfully, then the `mitm` begins a cycle where it relays data between the client and the server. When the data flow is from client to server, the `mitm.middleware.Middleware.client_data` function is called for all middlewares. When the data flow is from server to client, the `mitm.middleware.Middleware.server_data` function is called for all middlewares.

7. Once the server and client are done communicating, or the `mitm` server times out, the `mitm.middleware.Middleware.client_disconnected` and `mitm.middleware.Middleware.server_disconnected` function is called for all middlewares.

----

Customizing
***********

With the knowledge of the internals of `mitm`, we can move on to customizing `mitm` by adding custom protocols and middlewares. Checkout the next sections for more details.
