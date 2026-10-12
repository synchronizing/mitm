"""
Shared fixtures. Every test runs offline: origins are local servers, and ports are
picked by the OS.
"""

import gzip
import http.client
import http.server
import io
import ssl
import tempfile
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

import mitm
from mitm import MITM, CertificateAuthority, HTTPLog


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send(self, status, body=b"", content_type="text/plain", headers=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if self.path == "/hello":
            self.send(200, b"hello")
        elif self.path == "/gzip":
            self.send(200, gzip.compress(b'{"compressed": true}'), "application/json", [("Content-Encoding", "gzip")])
        elif self.path == "/binary":
            self.send(200, b"\x89PNG\r\n\x1a\n\x00\x00", "image/png")
        elif self.path == "/big":
            self.send(200, b"x" * 100_000)
        elif self.path == "/chunked":
            self.send_response(200)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in (b"first ", b"second"):
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
            self.wfile.write(b"0\r\n\r\n")
        elif self.path == "/close":
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(b"until close")
            self.close_connection = True
        else:
            self.send(404, b"not found")

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.send(200, body, self.headers["Content-Type"])


class Origin:
    """
    A local HTTP(S) server, run in a thread.
    """

    def __init__(self, context: ssl.SSLContext | None = None):
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        if context:
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture(autouse=True)
def data(tmp_path, monkeypatch) -> Path:
    """
    Keeps the default CA out of the real user data directory.
    """
    monkeypatch.setattr(mitm, "__data__", tmp_path)
    return tmp_path


@pytest.fixture(scope="session")
def ca() -> CertificateAuthority:
    """
    CA that signs both the origin's certificate and the proxy's, and is trusted by clients.
    """
    return CertificateAuthority()


@pytest.fixture(scope="session")
def ca_file(ca) -> str:
    path = Path(tempfile.mkdtemp()) / "ca.pem"
    path.write_bytes(ca.cert.public_bytes(serialization.Encoding.PEM))
    return str(path)


@pytest.fixture(scope="session")
def origin():
    server = Origin()
    yield server
    server.close()


@pytest.fixture(scope="session")
def tls_origin(ca):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    cert, key = ca.new_X509("localhost")
    with tempfile.TemporaryDirectory() as directory:
        cert_path, key_path = Path(directory) / "cert.pem", Path(directory) / "key.pem"
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(mitm.crypto.private_bytes(key))
        context.load_cert_chain(cert_path, key_path)
    server = Origin(context)
    yield server
    server.close()


@pytest.fixture
def log() -> HTTPLog:
    return HTTPLog(io.StringIO(), json=True, max_body=None)


@pytest.fixture
async def proxy(ca, ca_file, log):
    """
    A running proxy that logs to `log`, and trusts `ca` for upstream connections.
    """
    server = MITM(port=0, certificate_authority=ca, middlewares=[log])
    server.protocols[0].ssl_context.load_verify_locations(ca_file)
    async with server:
        yield server


def client_context(ca_file: str) -> ssl.SSLContext:
    return ssl.create_default_context(cafile=ca_file)


def request(proxy: MITM, method: str, url: str, body: bytes | None = None, headers=None, context=None):
    """
    Sends a request through `proxy` (blocking), and returns the response status and body.
    """
    scheme, _, rest = url.partition("://")
    authority, _, path = rest.partition("/")
    if scheme == "https":
        connection = http.client.HTTPSConnection("127.0.0.1", proxy.port, timeout=10, context=context)
        connection.set_tunnel(authority)
        target = "/" + path
    else:
        connection = http.client.HTTPConnection("127.0.0.1", proxy.port, timeout=10)
        target = url
    try:
        connection.request(method, target, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()
