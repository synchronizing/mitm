"""
Core components of the MITM framework.
"""

import asyncio
import ssl
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


@dataclass
class Host:
    """
    Dataclass representing an `mitm` host.

    A host is a pair of `asyncio.StreamReader` and `asyncio.StreamWriter` objects
    that are used to communicate with the remote host. There are two types of hosts: a
    client, and a server. A client host is one that is connected to the `mitm`, and a
    server host is one that the `mitm` connected to on behalf of the client.

    The `mitm_managed` attribute is used to determine whether the `mitm` should
    manage the host. If `mitm_managed` is `True`, the `mitm` will close the host
    when it is done with it. If `mitm_managed` is `False`, the `mitm` will not
    close the host.

    Note:
        See more on `dataclasses <https://docs.python.org/3/library/dataclasses.html>`_.

    Args:
        reader: The reader of the host.
        writer: The writer of the host.
        mitm_managed: Whether or not the host is managed by the `mitm`.

    Properties:
        reader: The reader of the host.
        writer: The writer of the host.
        mitm_managed: Whether or not the host is managed by the `mitm`.
        ip: The IP address of the host.
        port: The port of the host.

    Example:

        .. code-block:: python

            reader, writer = await asyncio.open_connection(...)
            server = Host(reader, writer)
    """

    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    mitm_managed: Optional[bool] = False

    def __post_init__(self):
        """
        Initializes the host and port information for the Host.

        This method is called by the Dataclass' `__init__` method post-initialization.
        """

        # At this point the self.writer is either None or a StreamWriter.
        if self.writer:
            self.host, self.port = self.writer._transport.get_extra_info("peername")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Sets Host attributes.

        We hijack this method to set the `host` and `port` attributes if/when the writer
        is set.
        """
        if (
            name == "writer"
            and isinstance(value, asyncio.StreamWriter)
            and not getattr(self, "host", None)
            and not getattr(self, "port", None)
        ):
            self.host, self.port = value._transport.get_extra_info("peername")
        return super().__setattr__(name, value)

    def __bool__(self):
        return self.reader is not None and self.writer is not None

    def __repr__(self):
        if self.reader:
            return f"Host({self.host}:{self.port}, mitm_managed={self.mitm_managed})"
        else:
            return f"Host(mitm_managed={self.mitm_managed})"

    def __str__(self):
        return f"{self.host}:{self.port}"


@dataclass
class Connection:
    """
    Dataclass representing a standard `mitm` connection.

    A connection is a pair of `Host` objects that the `mitm` relays data between. When
    a connection is created the server host is not resolved until the data is
    intercepted and the destination server is figured out.

    Note:
        See more on `dataclasses <https://docs.python.org/3/library/dataclasses.html>`_.

    Args:
        client: The client host.
        server: The server host.
        ssl_context: The SSL context of the connection.

    Example:
        .. code-block:: python

            client = Host(...)
            server = Host(...)
            ssl_context = ssl.SSLContext(...)

            connection = Connection(client, server, ssl_context)
    """

    client: Host
    server: Host
    ssl_context: ssl.SSLContext

    def __repr__(self):
        return f"<Connection client={self.client} server={self.server}>"


class Flow(Enum):
    """
    Enum representing the flow of the connection.

    Used within the :py:func:`mitm.MITM._relay` function to determine the flow of the
    connection for middleware purposes.

    Args:
        CLIENT_TO_SERVER: The client is sending data to the server.
        SERVER_TO_CLIENT: The server is sending data to the client.
    """

    CLIENT_TO_SERVER = 0
    SERVER_TO_CLIENT = 1
