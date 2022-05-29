"""
Core components of the MITM framework.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Tuple

from .crypto import CertificateAuthority


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
    mitm_managed: Optional[bool] = True

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
    intercepted and the protocol and destination server is figured out.

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

    def __repr__(self):
        return f"<Connection client={self.client} server={self.server}, protocol={self.protocol}>"


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


class Middleware(ABC):
    """
    Event-driven hook extension for the `mitm`.
    """

    @abstractmethod
    async def mitm_started(self, host: str, port: int):
        """
        Called when the mitm has started.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_connected(self, connection: Connection):
        """
        Called when the connection is established with the client.
        """
        raise NotImplementedError

    @abstractmethod
    async def server_connected(self, connection: Connection):
        """
        Called when the connection is established with the server.
        """
        raise NotImplementedError

    @abstractmethod
    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        """
        Called when data is received from the client.

        Note:
            Modifying the request will only modify the request sent to the destination
            server, and not the request mitm interprets. In other words, modifying the
            'Host' headers will not change the destination server.

            Raw TLS/SSL handshake is not sent through this method.

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

        Note:
            By the time this method is called, the server will have already successfully
            disconnected.
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<Middleware: {self.__class__.__name__}>"


class InvalidProtocol(Exception):
    """
    Exception raised when the protocol did not work.

    This is the only error that `mitm.MITM` will catch. Throwing this error will
    continue the search for a valid protocol.
    """


class Protocol(ABC):
    """
    An abstract class for a custom protocol implementation.

    The `bytes_needed` is used to determine the minimum number of bytes needed to be
    read from the connection to identify all of the protocols. This is done by getting
    the `max()` of the `bytes_needed` of all the protocols, and reading that many
    bytes from the connection.

    Args:
        bytes_needed: The minimum number of bytes needed to identify the protocol.

    Example:

        Template for a protocol implementation:

        .. code-block:: python

            from mitm import Protocol, Connection

            class MyProtocol(Protocol):
                bytes_needed = 4

                @classmethod
                async def connect(cls: Protocol, connection: Connection, data: bytes) -> bool:
                    # Do something with the data.
    """

    def __init__(
        self,
        bytes_needed: int = 8192,
        buffer_size: int = 8192,
        timeout: int = 15,
        keep_alive: bool = True,
        certificate_authority: CertificateAuthority = CertificateAuthority(),
        middlewares: List[Middleware] = [],
    ):
        self.bytes_needed = bytes_needed
        self.buffer_size = buffer_size
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.certificate_authority = certificate_authority
        self.middlewares = middlewares

    @abstractmethod
    async def resolve(self, connection: Connection, data: bytes) -> Optional[Tuple[str, int, bool]]:
        """
        Resolves the destination of the connection.

        Args:
            connection: Connection object containing a client host.
            data: The initial incoming data from the client.

        Returns:
            A tuple containing the host, port, and bool if the connection is encrypted.

        Raises:
            InvalidProtocol: If the connection failed.

        Note:
            This methods needs to be implemented by subclasses.
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

        Returns:
            Whether the connection was successful.

        Raises:
            InvalidProtocol: If the connection failed.

        Note:
            This methods needs to be implemented by subclasses.
        """
        raise NotImplementedError

    @abstractmethod
    async def handle(self, connection: Connection):
        """
        Handles the connection between a client and a server.

        Args:
            connection: Client/server connection to relay.

        Note:
            This methods needs to be implemented by subclasses.
        """
        raise NotImplementedError

    def __repr__(self):
        return f"<Protocol: {self.__class__.__name__}>"
