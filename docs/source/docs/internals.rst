###################
Internals of `mitm`
###################

Quick guide on the internal structure of `mitm`.

Make sure to check out the documentation for `asyncio streams <https://docs.python.org/3/library/asyncio-stream.html>`_ before reading this section.

----

Core
****

.. class:: mitm.models.Host

    A host is a pair of `asyncio.StreamReader` and `asyncio.StreamWriter` objects that are used to communicate with the remote host. There are two types of hosts: a client, and a server. A client host is one that is connected to the `mitm`, and a server host is one that the `mitm` connected to on behalf of the client.

    .. attribute:: reader

        The `asyncio.StreamReader` object for the host.

    .. attribute:: writer

        The `asyncio.StreamWriter` object for the host.

    .. attribute:: mitm_managed

        The `mitm_managed` attribute is used to determine whether the `mitm` is responsible for closing the connection with the host. If `mitm_managed` is True, the `mitm` will close the connection with the host when it is done with it. If `mitm_managed` is set to False, the `mitm` will not close the connection with the host, and instead, the developer must close the connection with the host manually. This is useful for situations where the `mitm` is running as a separate utility and the developer wants to keep the connection open with the host after the `mitm` is done with it.

    .. attribute:: host

        The IP address of the host, or `None` if not connected.

    .. attribute:: port

        The port of the host, or `None` if not connected.

    `Host` is a `dataclass <https://docs.python.org/3/library/dataclasses.html>`_ that is defined like so:

    .. code-block:: python

        @dataclass
        class Host:
            reader: asyncio.StreamReader | None = None
            writer: asyncio.StreamWriter | None = None
            mitm_managed: bool = True

.. class:: mitm.models.Connection

    A connection is a pair of `Host` objects that the `mitm` relays data between. When a connection is created the server host is not resolved until the data is intercepted and the protocol and destination server is figured out.

    .. attribute:: client

        The client `mitm.models.Host`. The client host connects to the `mitm`.

    .. attribute:: server

        The server `mitm.models.Host`. A server host is connected to the `mitm` on behalf of the client host.

    .. attribute:: protocol

        The `mitm.models.Protocol` object for the connection.

    `Connection` is a `dataclass <https://docs.python.org/3/library/dataclasses.html>`_ that is defined like so:

    .. code-block:: python

        @dataclass
        class Connection:
            client: Host
            server: Host
            protocol: Protocol | None = None

----

Extensions
**********

.. class:: mitm.models.Middleware

    Event-driven hook extension for the `mitm`.

    A middleware is a class that is used to extend the `mitm` framework by allowing event-driven hooks to be added to the `mitm` and executed when the appropriate event occurs. Built-in middlewares can be found in the `mitm.extension.middleware` module.

    Note that every hook is optional. Hooks that are not implemented do nothing, and the data hooks return the data untouched.

    .. method:: mitm_started(host: str, port: int)
        :async:

        Called when the `mitm` server boots-up.

    .. method:: client_connected(connection: Connection)
        :async:

        Called when a client connects to the `mitm` server. Note that the `mitm.models.Connection` object is not fully initialized yet, and only contains a valid client `mitm.models.Host`.

    .. method:: server_connected(connection: Connection)
        :async:

        Called when the `mitm` connects with the destination server. At this point the `mitm.models.Connection` object is fully initialized.

    .. method:: client_data(connection: Connection, data: bytes) -> bytes
        :async:

        Called when the `mitm` receives data from the client. The first call happens before the server is connected, and contains the request intended for the `mitm` (e.g. ``CONNECT``). Raw TLS/SSL handshake is not sent through this method. Everything should be decrypted beforehand.

        Note:
            This method **must** return back data. Modified or not.

    .. method:: server_data(connection: Connection, data: bytes) -> bytes
        :async:

        Called when the `mitm` receives data from the destination server. Data that comes through this hook can be modified and returned to the `mitm` as new data to be sent to the client.

        Note:
            This method **must** return back data. Modified or not.

    .. method:: client_disconnected(connection: Connection)
        :async:

        Called when the client disconnects.

    .. method:: server_disconnected(connection: Connection)
        :async:

        Called when the server disconnects.

    .. method:: connection_error(connection: Connection, error: Exception)
        :async:

        Called when the connection fails. For example, when the server cannot be reached, or when the client does not trust the `mitm` certificate. The 'disconnected' hooks are still called after this one.

.. class:: mitm.models.Protocol

    Protocols are implementations on how the data flows between the client and server. Application-layer protocols are implemented by subclassing this class. Built-in protocols can be found in the `mitm.extension` package.

    .. attribute:: bytes_needed

            Specifies how many bytes are needed to determine the protocol.

    .. attribute:: buffer_size

            The size of the buffer to use when reading data.

    .. attribute:: timeout

            The timeout to use when connecting to the server.

    Note that the attributes above must be set per-protocol basis.


    .. method:: resolve(connection: Connection, data: bytes) -> Tuple[str, int, bool]
        :async:

        Resolves the destination of the connection. Returns a tuple containing the host, port, and bool that indicates if the connection is encrypted. Raises `InvalidProtocol` if the data is not for this protocol.

    .. method:: connect(connection: Connection, host: str, port: int, tls: bool, data: bytes)
        :async:

        Attempts to connect to destination server using the given data, and sets ``connection.server`` if the connection was successful. Raises `InvalidProtocol` if the data is not for this protocol.

    .. method:: handle(connection: Connection)
        :async:

        Handles the connection between a client and a server.
