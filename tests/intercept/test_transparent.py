import asyncio
import socket
import struct

import pytest

from mitm import Connection, Host, InvalidProtocol, MITM, Middleware, Protocol
from mitm.proxy import original_dest_from_synthetic_connect, original_dest_from_tun


class Test_OriginalDestFromTUN:
    def test_ipv4_packet(self):
        packet = bytearray(24)
        packet[0] = 0x45
        packet[16:20] = socket.inet_aton("93.184.216.34")
        packet[22:24] = struct.pack("!H", 80)

        host, port = original_dest_from_tun(bytes(packet))

        assert host == "93.184.216.34"
        assert port == 80

    def test_ipv6_packet(self):
        packet = bytearray(44)
        packet[0] = 0x60
        packet[24:40] = socket.inet_pton(socket.AF_INET6, "2606:2800:220:1:248:1893:25c8:1946")
        packet[42:44] = struct.pack("!H", 443)

        host, port = original_dest_from_tun(bytes(packet))

        assert host == socket.inet_ntop(socket.AF_INET6, packet[24:40])
        assert port == 443

    def test_unknown_ip_version_raises(self):
        with pytest.raises(ValueError, match="Unknown IP version"):
            original_dest_from_tun(b"\x10\x00\x00\x00")


class Test_OriginalDestFromSyntheticConnect:
    @pytest.mark.asyncio
    async def test_https(self):
        data = b"CONNECT example.com:443 HTTP/1.1\r\nX-Mitm-Transparent: 1\r\nX-Mitm-TLS: 1\r\n\r\n"
        reader = asyncio.StreamReader()
        reader.feed_data(data)

        host, port, tls = await original_dest_from_synthetic_connect(reader)

        assert host == "example.com"
        assert port == 443
        assert tls is True

    @pytest.mark.asyncio
    async def test_http(self):
        data = b"CONNECT example.com:80 HTTP/1.1\r\nX-Mitm-Transparent: 1\r\n\r\n"
        reader = asyncio.StreamReader()
        reader.feed_data(data)

        host, port, tls = await original_dest_from_synthetic_connect(reader)

        assert host == "example.com"
        assert port == 80
        assert tls is False


class _NoopMiddleware(Middleware):
    async def mitm_started(self, host: str, port: int):
        return

    async def client_connected(self, connection: Connection):
        return

    async def server_connected(self, connection: Connection):
        return

    async def client_data(self, connection: Connection, data: bytes) -> bytes:
        return data

    async def server_data(self, connection: Connection, data: bytes) -> bytes:
        return data

    async def client_disconnected(self, connection: Connection):
        return

    async def server_disconnected(self, connection: Connection):
        return


class _RecordingProtocol(Protocol):
    bytes_needed = 1024
    buffer_size = 1024
    timeout = 1
    keep_alive = False

    def __init__(self, upstream_port: int):
        super().__init__()
        self.upstream_port = upstream_port
        self.resolve_called = False
        self.connect_args = None

    async def resolve(self, connection: Connection, data: bytes):
        self.resolve_called = True
        if b"X-Mitm-Transparent: 1" in data:
            raise InvalidProtocol
        return "example.com", 443, True

    async def connect(self, connection: Connection, host: str, port: int, tls: bool, data: bytes):
        self.connect_args = (host, port, tls, data)
        reader, writer = await asyncio.open_connection("127.0.0.1", self.upstream_port)
        connection.server = Host(reader=reader, writer=writer)

    async def handle(self, connection: Connection):
        return


class Test_TransparentMITMFlow:
    async def _wait_for_connect(self, protocol: _RecordingProtocol):
        for _ in range(20):
            if protocol.connect_args is not None:
                return
            await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_transparent_connect_bypasses_resolve_and_uses_tls_header(self):
        upstream = await asyncio.start_server(lambda _, __: None, host="127.0.0.1", port=0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        protocol = _RecordingProtocol(upstream_port)
        mitm = MITM(host="127.0.0.1", port=18901, protocols=[protocol], middlewares=[_NoopMiddleware()])

        async with mitm:
            _, writer = await asyncio.open_connection("127.0.0.1", 18901)
            writer.write(b"CONNECT example.com:80 HTTP/1.1\r\nX-Mitm-Transparent: 1\r\nX-Mitm-TLS: 1\r\n\r\n")
            await writer.drain()
            await self._wait_for_connect(protocol)
            writer.close()

        upstream.close()

        assert protocol.resolve_called is False
        assert protocol.connect_args == ("example.com", 80, True, b"")

    @pytest.mark.asyncio
    async def test_standard_connect_uses_resolve_path(self):
        upstream = await asyncio.start_server(lambda _, __: None, host="127.0.0.1", port=0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        protocol = _RecordingProtocol(upstream_port)
        mitm = MITM(host="127.0.0.1", port=18902, protocols=[protocol], middlewares=[_NoopMiddleware()])

        async with mitm:
            _, writer = await asyncio.open_connection("127.0.0.1", 18902)
            writer.write(b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n")
            await writer.drain()
            await self._wait_for_connect(protocol)
            writer.close()

        upstream.close()

        assert protocol.resolve_called is True
        assert protocol.connect_args == (
            "example.com",
            443,
            True,
            b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n",
        )
