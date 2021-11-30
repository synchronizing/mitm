######################
Custom `mitm.Protocol`
######################

Understanding and overview of a custom protocol. 

----

Protocol, in the context of `mitm`, is a user-implemented application-layer protocol that can be plugged into `mitm`. It can also be thought of as a two purpose concept: 

1. Protocol can be your standard application-layer protocol, such as HTTP, SMTP, SSH, etc., which can be implemented within the `mitm` framework to intercept and modify different types of traffics.

2. A protocol can also be seen as a way to modify and re-direct `mitm` traffic, such as redirecting traffic to a different host, or redirecting traffic to a different port.

Protocol is implemented as a class, and it is recommended that you implement a class that inherits from `mitm.protocol.Protocol`. An example of a custom protocol is the built-in HTTP protocol, whose code looks like so:

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
        async def connect(cls: Protocol, connection: Connection, data: bytes) -> bool:
            """
            Connects to the destination server if the data is a valid HTTP request.

            Args:
                connection: The connection to the destination server.
                data: The data received from the client.

            Returns:
                Whether the connection was successful.

            Raises:
                InvalidProtocol: If the connection failed.
            """
            try:
                request = httpq.Request.parse(data)
            except:
                raise InvalidProtocol

            # Deal with 'CONNECT'.
            if request.method == "CONNECT":

                # Get the hostname and port.
                if not request.target:
                    raise InvalidProtocol
                host, port = request.target.string.split(":")

                # Accept client connection.
                connection.client.writer.write(b"HTTP/1.1 200 OK\r\n\r\n")
                await connection.client.writer.drain()

                # Perform handshake.
                try:
                    await toolbox.tls_handshake(
                        reader=connection.client.reader,
                        writer=connection.client.writer,
                        ssl_context=connection.ssl_context,
                        server_side=True,
                    )
                except ssl.SSLError:
                    raise InvalidProtocol

                # Connect to destination server.
                reader, writer = await asyncio.open_connection(
                    host=host,
                    port=int(port),
                    ssl=True,
                )
                connection.server = Host(reader, writer)

                return True

            # Deal with any other HTTP method.
            elif request.method:

                # Get the hostname and port.
                if not "Host" in request.headers:
                    raise InvalidProtocol
                host, port = request.headers.get("Host").string, 80

                # Connect to destination server and send initial request.
                reader, writer = await asyncio.open_connection(
                    host=host,
                    port=port,
                    ssl=False,
                )
                connection.server = Host(reader, writer)
                connection.server.writer.write(data)
                await connection.server.writer.drain()

                return True

            raise InvalidProtocol

The code above is a `mitm` protocol that can be used to intercept HTTP traffic (with TLS/`CONNECT` support). Users of `mitm` can implement their own protocols as needed.
