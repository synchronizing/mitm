######################
Custom `mitm.Protocol`
######################

Understanding and overview of a custom protocol. 

----

Protocol, in the context of `mitm`, is a user-implemented `application-layer protocol <https://en.wikipedia.org/wiki/Application_layer>`_ that can be plugged into `mitm`. It's intended to be used as an interface that can decipher *where* the client is trying to go, and connect them to it.  Protocol is implemented as a class, and it is recommended that you implement a class that directly inherit from `mitm.protocol.Protocol`.

The `mitm.protocol.Protocol` has two abstract methods: 

.. class:: mitm.Protocol

    .. attribute:: bytes_needed

            Class attribute that specifies how many bytes are needed to determine the protocol.

    .. method:: resolve_destination(cls: Protocol, connection: Connection, data: bytes)
            :async:
            :staticmethod:

            Resolves the destination of the connection.

    .. method:: connect(cls: Protocol, connection: Connection, data: bytes)
            :async:
            :staticmethod:

            Connects the client to the destination server.

            `data` is a bytes object with length of the largest `bytes_needed` of all protocols.

----

Application-layer Protocol
**************************

The code below is the `mitm` protocol that can be used to intercept HTTP traffic (with TLS/`CONNECT` support). Users of `mitm` can implement their own protocols as needed. 

.. code-block:: python

    class HTTP(Protocol):

        # We need 8192 bytes to determine if the connection is HTTP.
        bytes_needed = 8192

        @classmethod
        async def resolve_destination(
            cls: Protocol,
            connection: Connection,
            data: bytes,
        ) -> Tuple[str, int, bool]:
            try:
                request = Request.parse(data)
            except:
                raise InvalidProtocol

            # Deal with 'CONNECT'.
            tls = None
            if request.method == "CONNECT":
                tls = True

                # Get the hostname and port.
                if not request.target:
                    raise InvalidProtocol
                host, port = request.target.string.split(":")

                # Accept client connection.
                connection.client.writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
                await connection.client.writer.drain()

                # Perform handshake.
                try:
                    await tls_handshake(
                        reader=connection.client.reader,
                        writer=connection.client.writer,
                        ssl_context=connection.ssl_context,
                        server_side=True,
                    )
                except ssl.SSLError:
                    raise InvalidProtocol

            # Deal with any other HTTP method.
            elif request.method:
                tls = False

                # Get the hostname and port.
                if not "Host" in request.headers:
                    raise InvalidProtocol
                host, port = request.headers.get("Host").string, 80

            return host, int(port), tls


        @classmethod
        async def connect(cls: Protocol, connection: Connection, data: bytes) -> bool:
            # Resolves destination to host.
            host, port, tls = await cls.resolve_destination(connection, data)

            # Connect to destination server and send initial request.
            reader, writer = await asyncio.open_connection(
                host=host,
                port=port,
                ssl=tls,
            )
            connection.server = Host(reader, writer)

            # Send initial request if not SSL/TLS connection.
            if not tls:
                connection.server.writer.write(data)
                await connection.server.writer.drain()

            return True
