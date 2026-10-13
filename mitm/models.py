"""
Core components of the MITM framework.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from mitm.crypto import CertificateAuthority


@dataclass
class Host:
    """
    Dataclass representing an `mitm` host.

    A host is a pair of `asyncio.StreamReader` and `asyncio.StreamWriter` objects
    that are used to communicate with the remote host. There are two types of hosts: a
    client, and a server. A client host is one that is connected to the `mitm`, and a
    server host is one that the `mitm` connected to on behalf of the client.

    The `mitm_managed` attribute is used to determine whether the `mitm` is responsible
    for closing the connection with the host. If `mitm_managed` is True, the `mitm` will
    close the connection with the host when it is done with it. If `mitm_managed` is set
    to False, the `mitm` will not close the connection with the host, and instead, the
    developer must close the connection with the host manually. This is useful for
    situations where the `mitm` is running as a separate utility and the developer
    wants to keep the connection open with the host after the `mitm` is done with it.

    Note:
        See more on `dataclasses <https://docs.python.org/3/library/dataclasses.html>`_.

    Args:
        reader: The reader of the host.
        writer: The writer of the host.
        mitm_managed: Whether or not the host is managed by the `mitm`.

    Attributes:
        reader: The reader of the host.
        writer: The writer of the host.
        mitm_managed: Whether or not the host is managed by the `mitm`.
        host: The IP address of the host, or `None` if the host is not connected.
        port: The port of the host, or `None` if the host is not connected.

    Example:

        .. code-block:: python

            reader, writer = await asyncio.open_connection(...)
            server = Host(reader, writer)
    """

    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    mitm_managed: Optional[bool] = True

    @property
    def host(self) -> Optional[str]:
        """
        Returns the IP address of the host.
        """
        peername = self.writer.get_extra_info("peername") if self.writer else None
        return peername[0] if peername else None

    @property
    def port(self) -> Optional[int]:
        """
        Returns the port of the host.
        """
        peername = self.writer.get_extra_info("peername") if self.writer else None
        return peername[1] if peername else None

    def __bool__(self) -> bool:
        """
        Returns whether or not the host is connected.
        """
        return self.reader is not None and self.writer is not None

    def __repr__(self) -> str:
        """
        Returns a string representation of the host.
        """
        if self.reader and self.writer:
            return f"Host({self.host}:{self.port}, mitm_managed={self.mitm_managed})"

        return f"Host(mitm_managed={self.mitm_managed})"

    def __str__(self) -> str:
        """
        Returns a string representation of the host.
        """
        if self.reader and self.writer:
            return f"{self.host}:{self.port}"

        return "<empty host>"


@dataclass
class Connection:
    """
    Dataclass representing a standard `mitm` connection.

    A connection is a pair of `Host` objects that the `mitm` relays data between. When a
    connection is created the server host is not resolved until the data is intercepted
    and the protocol and destination server is figured out.

    Note:
        See more on `dataclasses <https://docs.python.org/3/library/dataclasses.html>`_.

    Args:
        client: The client host.
        server: The server host.
        protocol: The protocol of the connection.

    Example:
        .. code-block:: python

            client = Host(...)
            server = Host(...)

            connection = Connection(client, server, HTTP())
    """

    client: Host
    server: Host
    protocol: Optional[Protocol] = None

    def __repr__(self) -> str:
        return f"Connection(client={self.client}, server={self.server}, protocol={self.protocol})"


class Flow(Enum):
    """
    Enum representing the flow of the connection.

    Can be used within the appropriate locations to determine the flow of the
    connection. Not used by the core `mitm` framework, but used by the HTTP extension.

    Args:
        CLIENT_TO_SERVER: The client is sending data to the server.
        SERVER_TO_CLIENT: The server is sending data to the client.
    """

    CLIENT_TO_SERVER = 0
    SERVER_TO_CLIENT = 1


class Middleware(ABC):
    """
    Event-driven hook extension for the `mitm`.

    A middleware is a class that is used to extend the `mitm` framework by allowing
    event-driven hooks to be added to the `mitm` and executed when the appropriate
    event occurs. Built-in middlewares can be found in the `mitm.extension.middleware`
    module.

    Note:
        Every hook is optional. Hooks that are not implemented do nothing, and the data
        hooks return the data untouched.

    Example:

        .. code-block:: python

            from mitm import MITM, Middleware

            class Uppercase(Middleware):
                async def server_data(self, connection, data):
                    return data.upper()

            MITM(middlewares=[Uppercase]).run()
    """

    async def mitm_started(self, host: str, port: int):
        """
        Called when the `mitm` server boots-up.
        """

    async def client_connected(self, connection: Connection):
        """
        Called when the connection is established with the client.

        Note:
            Note that the `mitm.models.Connection` object is not fully initialized yet,
            and only contains a valid client `mitm.models.Host`.
        """

    async def server_connected(self, connection: Connection):
        """
        Called when the connection is established with the server.

        Note:
            At this point the `mitm.models.Connection` object is fully initialized.
        """

    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        """
        Called when data is received from the client.

        Note:
            The first call for a connection happens before the server is connected, and
            contains the request intended for the `mitm` (e.g. 'CONNECT'). Raw TLS/SSL
            handshake is not sent through this method. Everything should be decrypted
            beforehand.

        Args:
            connection: The connection the data was received on.
            data: The data received from the client.

        Returns:
            The data to send to the server.
        """
        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        """
        Called when data is received from the server.

        Args:
            connection: The connection the data was received on.
            data: The data received from the server.

        Returns:
            The data to send back to the client.
        """
        return data

    async def client_disconnected(self, connection: Connection):
        """
        Called when the client disconnects.
        """

    async def server_disconnected(self, connection: Connection):
        """
        Called when the server disconnects.
        """

    async def connection_error(self, connection: Connection, error: Exception):
        """
        Called when the connection fails. For example, when the server cannot be reached,
        or when the client does not trust the `mitm` certificate.

        Note:
            The 'disconnected' hooks are still called after this one.
        """

    def __repr__(self) -> str:
        return f"Middleware({self.__class__.__name__})"


class InvalidProtocol(Exception):
    """
    Exception raised when the protocol did not work.

    Throwing this error from `Protocol.resolve` or `Protocol.connect` will continue the
    search for a valid protocol.
    """


class Protocol(ABC):  # pragma: no cover
    """
    Custom protocol implementation.

    Protocols are implementations on how the data flows between the client and server.
    Application-layer protocols are implemented by subclassing this class. Built-in
    protocols can be found in the `mitm.extension` package.

    Parameters:
        bytes_needed: Minimum number of bytes needed to determine the protocol.
        buffer_size: The size of the buffer to use when reading data.
        timeout: The timeout to use when connecting to the server.
    """

    bytes_needed: int
    buffer_size: int
    timeout: int

    def __init__(
        self,
        certificate_authority: Optional[CertificateAuthority] = None,
        middlewares: Optional[List[Middleware]] = None,
    ):
        """
        Initializes the protocol.

        Args:
            certificate_authority: The certificate authority to use for the connection.
            middlewares: The middlewares to use for the connection.
        """
        self.certificate_authority = certificate_authority if certificate_authority else CertificateAuthority()
        self.middlewares = middlewares if middlewares else []

    @abstractmethod
    async def resolve(self, connection: Connection, data: bytes) -> Tuple[str, int, bool]:
        """
        Resolves the destination of the connection.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Returns:
            A tuple containing the host, port, and bool that indicates if the connection
            is encrypted.

        Raises:
            InvalidProtocol: If the data is not for this protocol.
        """
        raise NotImplementedError

    @abstractmethod
    async def connect(self, connection: Connection, host: str, port: int, tls: bool, data: bytes):
        """
        Attempts to connect to destination server using the given data, and sets
        `connection.server` if the connection was successful.

        Args:
            connection: Connection object containing a client host.
            host: The hostname of the destination server.
            port: The port of the destination server.
            tls: Whether the connection is encrypted.
            data: The initial incoming data from the client.

        Raises:
            InvalidProtocol: If the data is not for this protocol.
        """
        raise NotImplementedError

    @abstractmethod
    async def handle(self, connection: Connection):
        """
        Handles the connection between a client and a server.

        Args:
            connection: Client/server connection to relay.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"Protocol({self.__class__.__name__})"
