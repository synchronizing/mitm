"""HTTP request and response parsing."""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import Any, Optional, Union

from mitm.utils.http.item import (
    Item,
    ItemDict,
    ItemType,
    MultiEntryDict,
    ObjectDict,
    OverloadedDict,
    UnderscoreAccessDict,
)


class state(enum.Enum):
    """
    States of the HTTP request.
    """

    TOP = 0
    HEADER = 1
    BODY = 2


class Headers(ItemDict, ObjectDict, OverloadedDict, UnderscoreAccessDict, MultiEntryDict):
    """
    Container for HTTP headers.
    """

    def _compile(self) -> bytes:
        """
        Compile the headers.
        """
        lines = []
        for k, v in self.items():
            if isinstance(v, list):
                string = b"%s: " % k.raw + b", ".join([i.raw for i in self[k]]) + b"\r\n"
            else:
                string = b"%s: %s\r\n" % (k.raw, v.raw)

            lines.append(string)

        return b"%s\r\n" % b"".join(lines)

    def __setitem__(self, key: Any, value: Any):
        """
        Deletes the previous value of the item and sets the new value.

        Args:
            key: The key of the item.
            value: The value of the item.
        """
        if key in self:
            del self[key]

        super().__setitem__(key, value)

    def __defaultsetitem__(self, key: Any, value: Any):
        """
        Sets the value of the item without deleting the previous value.

        Args:
            key: The key of the item.
            value: The value of the item.
        """
        super().__setitem__(key, value)

    @property
    def raw(self) -> bytes:
        """
        The raw headers.
        """
        return self._compile()


InpType = Optional[ItemType]
HeadersType = Union[Headers, dict]


class Message(ABC):
    __slots__ = ("body", "buffer", "headers", "protocol")

    def __init__(
        self,
        protocol: InpType = None,
        headers: HeadersType = {},
        body: InpType = None,
    ):
        """
        Initializes an HTTP message.

        Args:
            protocol: The protocol of the HTTP message.
            headers: The headers of the HTTP message.
            body: The body of the HTTP message.

        Note:
            :py:class:`Message` is the base class for :py:class:`Request` and
            :py:class:`Response`, and is not intended to be used directly.
        """
        self.protocol = protocol
        self.headers = headers
        self.body = body
        self.buffer = b""

    def __setattr__(self, name: str, value: Any):
        """
        Sets the value of the attribute. Defaults to ``toolbox.collections.Item``.

        Args:
            name: The name of the attribute.
            value: The value of the attribute.
        """
        if name == "headers":
            super().__setattr__(name, Headers(value))
        elif name == "buffer":
            super().__setattr__(name, value)
        else:
            super().__setattr__(name, Item(value))

    def feed(self, msg: bytes) -> state:
        """
        Adds chuncks of the message to the internal buffer.

        Args:
            msg: The message to add to the internal buffer.
        """

        # Checks the msg type:
        if not isinstance(msg, bytes):
            raise TypeError("Message must be bytes.")

        self.buffer += msg
        return self.state

    @property
    def state(self) -> state:
        if self.buffer.count(b"\r\n") > 0 and b"\r\n\r\n" not in self.buffer:
            return state.HEADER
        elif self.buffer.count(b"\r\n") == 0:
            return state.TOP

        current = state.TOP
        _, body = self.buffer.split(b"\r\n\r\n", 1)

        # Split the message into lines.
        for line in self.buffer.split(b"\r\n"):
            # Parses the first line of the HTTP/1.1 msg.
            if current == state.TOP:
                self._parse_top(line)
                current = state.HEADER

            # Parse the headers of the HTTP/1.1 msg.
            elif current == state.HEADER:
                if b":" in line:
                    key, value = line.split(b":", 1)

                    if b"," in value:
                        value = value.split(b",")
                    else:
                        value = [value]

                    for v in value:
                        if key not in self.headers or v.strip() not in self.headers[key]:
                            self.headers.__defaultsetitem__(key, v.strip())
                else:
                    current = state.BODY

        if current == state.BODY:
            self.body = body

        return current

    @abstractmethod
    def _parse_top(self, line: bytes):  # pragma: no cover
        """
        Parses the first line of the HTTP message.
        """
        raise NotImplementedError

    @classmethod
    def parse(cls, msg: bytes) -> "Message":
        """
        Parses a complete HTTP message.

        Args:
            msg: The message to parse.
        """
        obj = cls()
        obj.feed(msg)
        return obj

    @abstractmethod
    def _compile_top(self) -> bytes:  # pragma: no cover
        """
        Compiles the first line of the HTTP message.
        """
        raise NotImplementedError

    def _compile(self) -> bytes:
        """
        Compiles a complete HTTP message.
        """
        return b"%s%s%s" % (self._compile_top(), self.headers.raw, self.body.raw)

    @property
    def raw(self) -> bytes:
        """
        Returns the raw (bytes) HTTP message.
        """
        return self._compile()

    def __eq__(self, other: Message) -> bool:
        """
        Compares two HTTP messages.
        """
        return self.raw == other.raw

    def __str__(self) -> str:
        """
        Pretty-print of the HTTP message.
        """

        if self.__class__ == Request:
            arrow = "→ "
        elif self.__class__ == Response:
            arrow = "← "
        else:  # pragma: no cover
            arrow = "? "

        return arrow + arrow.join(self._compile().decode("utf-8").rstrip("\r\n").splitlines(True))


class Request(Message):
    __slots__ = Message.__slots__ + ("method", "target")

    def __init__(
        self,
        method: InpType = None,
        target: InpType = None,
        protocol: InpType = None,
        headers: HeadersType = {},
        body: InpType = None,
    ):
        """
        Initializes an HTTP request.

        Args:
            method: The method of the HTTP request.
            target: The target of the HTTP request.
            protocol: The protocol of the HTTP request.
            headers: The headers of the HTTP request.
            body: The body of the HTTP request.
        """
        super().__init__(protocol, headers, body)
        self.method = method
        self.target = target

        objs = [self.method, self.target, self.protocol]
        if all(obj == None for obj in objs):
            self.buffer = b""
        elif all(obj for obj in objs):
            self.buffer = b"%s %s %s\r\n" % (
                self.method.raw,
                self.target.raw,
                self.protocol.raw,
            )
        else:
            raise ValueError("Request must have method, target, and protocol.")

        if self.headers:
            self.buffer += self.headers.raw + b"\r\n\r\n"

        if self.body:
            self.buffer += self.body.raw

    def _parse_top(self, line: bytes):
        """
        Parses the first line of the HTTP request.
        """
        self.method, self.target, self.protocol = line.split(b" ")

    def _compile_top(self):
        """
        Compiles the first line of the HTTP request.
        """
        return b"%s %s %s\r\n" % (self.method.raw, self.target.raw, self.protocol.raw)


class Response(Message):
    __slots__ = Message.__slots__ + ("status", "reason")

    def __init__(
        self,
        protocol: InpType = None,
        status: InpType = None,
        reason: InpType = None,
        headers: HeadersType = {},
        body: InpType = None,
    ):
        """
        Initializes an HTTP response.

        Args:
            protocol: The protocol of the HTTP response.
            status: The status of the HTTP response.
            reason: The reason of the HTTP response.
            headers: The headers of the HTTP response.
            body: The body of the HTTP response.
        """
        super().__init__(protocol, headers, body)
        self.status = status
        self.reason = reason

        objs = [self.protocol, self.status, self.reason]
        if all(obj == None for obj in objs):
            self.buffer = b""
        elif all(obj for obj in objs):
            self.buffer = b"%s %s %s\r\n" % (
                self.protocol.raw,
                self.status.raw,
                self.reason.raw,
            )
        else:
            raise ValueError("Response must have protocol, status, and reason.")

        if self.headers:
            self.buffer += self.headers.raw + b"\r\n\r\n"

        if self.body:
            self.buffer += self.body.raw

    def _parse_top(self, line: bytes):
        """
        Parses the first line of the HTTP response.
        """
        self.protocol, self.status, self.reason = line.split(b" ")

    def _compile_top(self) -> bytes:
        """
        Parses the first line of the HTTP response.
        """
        return b"%s %s %s\r\n" % (self.protocol.raw, self.status.raw, self.reason.raw)


__all__ = ["Request", "Response", "Headers", "state"]
