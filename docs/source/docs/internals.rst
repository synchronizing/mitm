###################
Internals of `mitm`
###################

Quick guide on the internal structure of `mitm`.

Make sure to check out the documentation for `asyncio streams <https://docs.python.org/3/library/asyncio-stream.html>`_ before reading this section.

----

Core
****

.. class:: mitm.core.Host

    A host is a pair of `asyncio.StreamReader` and `asyncio.StreamWriter` objects that are used to communicate with the remote host. There are two types of hosts: a client, and a server. A client host is one that is connected to the `mitm`, and a server host is one that the `mitm` connected to on behalf of the client.

    .. attribute:: reader

        The `asyncio.StreamReader` object for the host.

    .. attribute:: writer

        The `asyncio.StreamWriter` object for the host.

    .. attribute:: mitm_managed

        The `mitm_managed` attribute is used to determine whether the `mitm` is responsible for closing the connection with the host. If `mitm_managed` is True, the `mitm` will close the connection with the host when it is done with it. If `mitm_managed` is set to False, the `mitm` will not close the connection with the host, and instead, the developer must close the connection with the host manually. This is useful for situations where the `mitm` is running as a seperate utility and the developer wants to keep the connection open with the host after the `mitm` is done with it.

    .. attribute:: ip

        The IP address of the host.

    .. attribute:: port

        The port of the host.

    `Host` is a `dataclass <https://docs.python.org/3/library/dataclasses.html>`_ that is defined like so:

    .. code-block:: python

        @dataclass
        class Host:
            reader: Optional[asyncio.StreamReader] = None
            writer: Optional[asyncio.StreamWriter] = None
            mitm_managed: Optional[bool] = True

.. class:: mitm.core.Connection

    A connection is a pair of `Host` objects that the `mitm` relays data between. When a connection is created the server host is not resolved until the data is intercepted and the protocol and destination server is figured out.

    .. attribute:: client

        The client `mitm.core.Host`. The client host connects to the `mitm`.

    .. attribute:: server

        The server `mitm.core.Host`. A server host is connected to the `mitm` on behalf of the client host.

    .. attribute:: protocol

        The `mitm.core.Protocol` object for the connection.

    `Connection` is a `dataclass <https://docs.python.org/3/library/dataclasses.html>`_ that is defined like so:

    .. code-block:: python

        @dataclass
        class Connection:
            client: Host
            server: Host
            protocol: Optional[Protocol] = None

----

Extensions
**********

.. class:: mitm.core.Middleware

    Event-driven hook extension for the `mitm`.

    A middleware is a class that is used to extend the `mitm` framework by allowing event-driven hooks to be added to the `mitm` and executed when the appropriate event occurs. Built-in middlewares can be found in the `mitm.middleware` module.

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

    .. method:: client_data(connection: Connection, data: bytes) -> bytes
        :async:
        :staticmethod:
        
        Raw TLS/SSL handshake is not sent through this method. Everything should be decrypted beforehand.

        Note:
            This method **must** return back data. Modified or not.

    .. method:: server_data(connection: Connection, data: bytes) -> bytes
        :async:
        :staticmethod:

        Called when the `mitm` receives data from the destination server. Data that comes through this hook can be modified and returned to the `mitm` as new data to be sent to the client.

        Note:
            This method **must** return back data. Modified or not.  

    .. method:: client_disconnected(connection: Connection)
        :async:
        :staticmethod:

        Called when the client disconnects.

    .. method:: server_disconnected(connection: Connection)
        :async:
        :staticmethod:

        Called when the server disconnects.

.. class:: mitm.core.Protocol

    Protocols are implementations on how the data flows between the client and server. Application-layer protocols are implemented by subclassing this class. Built-in protocols can be found in the `mitm.extension` package.

    .. attribute:: bytes_needed

            Specifies how many bytes are needed to determine the protocol.

    .. attribute:: buffer_size

            The size of the buffer to use when reading data.

    .. attribute:: timeout

            The timeout to use when reading data.

    .. attribute:: keep_alive

            Whether or not to keep the connection alive.

    Note that the attributes above must be set per-protocol basis.


    .. method:: resolve(connection: Connection, data: bytes) -> Tuple[str, int, bool]
        :async:

        Resolves the destination of the connection. Returns a tuple containing the host, port, and bool that indicates if the connection is encrypted.

    .. method:: connect(connection: Connection, host: str, port: int, data: bytes)
        :async:

        Attempts to connect to destination server using the given data. Returns `True` if the connection was successful, raises `InvalidProtocol` if the connection failed.
        
    .. method:: handle(connection: Connection)
        :async:

        Handles the connection between a client and a server.
