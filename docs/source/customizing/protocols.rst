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
        """
        Adds support for HTTP protocol (with TLS support).

        This protocol adds HTTP and HTTPS proxy support to the `mitm`. Note that by
        "HTTPS proxy" we mean a proxy that supports the `CONNECT` statement, and not
        one that instantly performs a TLS handshake on connection with the client (though
        this can be added if needed).

        `bytes_needed` is set to 8192 to ensure we can read the first line of the request.
        The HTTP/1.1 protocol does not define a minimum length for the first line, so we
        use the largest number found in other projects.
        """

        bytes_needed = 8192

        @classmethod
        async def resolve_destination(
            cls: Protocol,
            connection: Connection,
            data: bytes,
        ) -> Tuple[str, int, str]:
            """
            Resolves the destination server for the protocol.
            """
            try:
                request = Request.parse(data)
            except:
                raise InvalidProtocol

            # Deal with 'CONNECT'.
            certificate = None
            if request.method == "CONNECT":

                # Get the hostname and port.
                if not request.target:
                    raise InvalidProtocol
                host, port = request.target.string.split(":")

                # Accept client connection.
                connection.client.writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
                await connection.client.writer.drain()

                # Retrieves the server's certificate.
                certificate = ssl.get_server_certificate((host, port))

            # Deal with any other HTTP method.
            elif request.method:

                # Get the hostname and port.
                if not "Host" in request.headers:
                    raise InvalidProtocol
                host, port = request.headers.get("Host").string, 80

            return host, int(port), certificate

        @classmethod
        async def connect(cls: Protocol, connection: Connection, data: bytes, ca: CertificateAuthority) -> bool:
            """
            Connects to the destination server if the data is a valid HTTP request.

            Args:
                connection: The connection to the destination server.
                data: The data received from the client.
                ca: The certificate authority to use for TLS handshakes.

            Returns:
                Whether the connection was successful.

            Raises:
                InvalidProtocol: If the connection failed.
            """

            # Resolves destination to host.
            host, port, certificate = await cls.resolve_destination(connection, data)

            # Generate certificate if TLS.
            if certificate:

                # Creates a copy of the SSL context, and signs it with the CA.
                cert, key = ca.new_cert(host)
                ssl_context = new_context(cert, key)

                # Perform handshake.
                try:
                    await tls_handshake(
                        reader=connection.client.reader,
                        writer=connection.client.writer,
                        ssl_context=ssl_context,
                        server_side=True,
                    )
                except ssl.SSLError:
                    raise InvalidProtocol

            # Connect to destination server and send initial request. Unfortunately due to
            # some unknown bug with asyncio we are unable to extract the certificate from
            # the server via 'asyncio.open_connection' before tls_handshake is called. We
            # open two indepedent connections to the server, one to retrieve the
            # certificate, and one to send the request.
            reader, writer = await asyncio.open_connection(
                host=host,
                port=port,
                ssl=bool(certificate),
            )
            connection.server = Host(reader, writer)

            # Send initial request if not SSL/TLS connection.
            if not certificate:
                connection.server.writer.write(data)
                await connection.server.writer.drain()

            return True
