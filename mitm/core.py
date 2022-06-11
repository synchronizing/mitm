"""
Core components of the MITM framework.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Tuple

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
    situations where the `mitm` is running as a seperate utility and the developer
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
        ip: The IP address of the host.
        port: The port of the host.

    Example:

        .. code-block:: python

            reader, writer = await asyncio.open_connection(...)
            server = Host(reader, writer)
    """

    reader: Optional[asyncio.StreamReader] = None
    writer: Optional[asyncio.StreamWriter] = None
    mitm_managed: Optional[bool] = True

    def __post_init__(self):
        """
        Initializes the host and port information for the Host.

        This method is called by the Dataclass' `__init__` method post-initialization.
        """

        # At this point the self.writer is either None or a StreamWriter.
        if self.writer:
            self.host, self.port = self.writer._transport.get_extra_info("peername")  # pylint: disable=protected-access

    def __setattr__(self, name: str, value: Any):
        """
        Sets Host attributes.

        We hijack this method to set the `host` and `port` attributes if/when the writer
        is set. This is because the `host` and `port` attributes are not set until the
        writer is set.

        Args:
            name: The name of the attribute to set.
            value: The value of the attribute to set.
        """
        if (
            name == "writer"
            and isinstance(value, asyncio.StreamWriter)
            and not getattr(self, "host", None)
            and not getattr(self, "port", None)
        ):
            self.host, self.port = value._transport.get_extra_info("peername")
        return super().__setattr__(name, value)

    def __bool__(self) -> bool:
        """
        Returns whether or not the host is connected.
        """
        return self.reader is not None and self.writer is not None

    def __repr__(self) -> str:  # pragma: no cover
        """
        Returns a string representation of the host.
        """
        if self.reader and self.writer:
            return f"Host({self.host}:{self.port}, mitm_managed={self.mitm_managed})"

        return f"Host(mitm_managed={self.mitm_managed})"

    def __str__(self) -> str:  # pragma: no cover
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

            connection = Connection(client, server, Protocol.HTTP)
    """

    client: Host
    server: Host
    protocol: Optional[Protocol] = None

    def __repr__(self) -> str:  # pragma: no cover
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


class Middleware(ABC):  # pragma: no cover
    """
    Event-driven hook extension for the `mitm`.

    A middleware is a class that is used to extend the `mitm` framework by allowing
    event-driven hooks to be added to the `mitm` and executed when the appropriate
    event occurs. Built-in middlewares can be found in the `mitm.middleware` module.
    """

    @abstractmethod
    async def mitm_started(self, host: str, port: int):
        """
        Called when the `mitm` server boots-up.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_connected(self, connection: Connection):
        """
        Called when the connection is established with the client.

        Note:
            Note that the `mitm.core.Connection` object is not fully initialized yet,
            and only contains a valid client `mitm.core.Host`.
        """
        raise NotImplementedError

    @abstractmethod
    async def server_connected(self, connection: Connection):
        """
        Called when the connection is established with the server.

        Note:
            At this point the `mitm.core.Connection` object is fully initialized.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        """
        Called when data is received from the client.

        Note:
            Modifying the request will only modify the request sent to the destination
            server, and not the first request mitm interprets. In other words, modifying
            the 'Host' headers will not change the destination server.

            Raw TLS/SSL handshake is not sent through this method. Everything should be
            decrypted beforehand.

        Args:
            request: The request received from the client.

        Returns:
            The request to send to the server.
        """
        raise NotImplementedError

    @abstractmethod
    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        """
        Called when data is received from the server.

        Args:
            response: The response received from the server.

        Returns:
            The response to send back to the client.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_disconnected(self, connection: Connection):
        """
        Called when the client disconnects.
        """
        raise NotImplementedError

    @abstractmethod
    async def server_disconnected(self, connection: Connection):
        """
        Called when the server disconnects.
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"Middleware({self.__class__.__name__})"


class InvalidProtocol(Exception):  # pragma: no cover
    """
    Exception raised when the protocol did not work.

    This is the only error that `mitm.MITM` will catch. Throwing this error will
    continue the search for a valid protocol.
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
        timeout: The timeout to use when reading data.
        keep_alive: Whether or not to keep the connection alive.
    """

    bytes_needed: int
    buffer_size: int
    timeout: int
    keep_alive: bool

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
            InvalidProtocol: If the connection failed.
        """
        raise NotImplementedError

    @abstractmethod
    async def connect(self, connection: Connection, host: str, port: int, tls: bool, data: bytes):
        """
        Attempts to connect to destination server using the given data. Returns `True`
        if the connection was successful, raises `InvalidProtocol` if the connection
        failed.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Raises:
            InvalidProtocol: If the connection failed.
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

    def __repr__(self) -> str:  # pragma: no cover
        return f"Protocol({self.__class__.__name__})"
