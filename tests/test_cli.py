import asyncio
import json
import socket
import ssl
import subprocess
import sys
from pathlib import Path

import pytest

import mitm
from mitm import MITM, cli

from .conftest import HOST


def python(code):
    """
    Arguments that wrap a Python script.
    """
    return ["--", sys.executable, "-c", code]


def fetch(url):
    """
    Arguments that wrap a Python script that fetches the URL, and prints the response.
    """
    return python(f"import urllib.request; print(urllib.request.urlopen({url!r}).read().decode())")


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    """
    Removes the environment variables that change how the command is wrapped.
    """
    for key in ("NO_PROXY", "no_proxy", "NO_COLOR"):
        monkeypatch.delenv(key, raising=False)


def test_wrap(server, capfd):
    url = f"http://{HOST}:{server.port}/hello"
    assert cli.main(fetch(url)) == 0

    # The command's output is in stdout, and the traffic is in stderr.
    out, err = capfd.readouterr()
    assert out == "hello\n"
    assert err.startswith(f"  ┊ GET {url} → 200 OK (text/plain, 5 B, ")


def test_wrap_https(tls_server, ca_file, tmp_path, monkeypatch, capfd):

    # The 'mitm' trusts the local server, and the command trusts the 'mitm' (through the
    # 'SSL_CERT_FILE' variable).
    create_default_context = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda: create_default_context(cafile=ca_file))

    output = tmp_path / "traffic.jsonl"
    url = f"https://localhost:{tls_server.port}/hello"
    assert cli.main(["--json", "-o", str(output), *fetch(url)]) == 0
    assert capfd.readouterr() == ("hello\n", "")

    [entry] = [json.loads(line) for line in output.read_text().splitlines()]
    assert entry["request"]["url"] == url
    assert entry["response"]["body"] == "hello"


def test_wrap_verbose(server, capfd):
    assert cli.main(["-v", "--max-body", "3", *fetch(f"http://{HOST}:{server.port}/hello")]) == 0

    err = capfd.readouterr().err
    assert f"  ┊ Host: {HOST}" in err
    assert "  ┊ hel\n  ┊ … truncated (5 B received)" in err


def test_wrap_exit_code(capfd):
    assert cli.main(python("raise SystemExit(3)")) == 3
    assert "no traffic captured" in capfd.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="Windows does not support signals.")
def test_wrap_killed():

    # Commands killed by a signal exit with 128 + the signal number.
    assert cli.main(python("import os, signal; os.kill(os.getpid(), signal.SIGTERM)")) == 128 + 15


def test_wrap_command_not_found(capfd):
    assert cli.main(["--", "mitm-no-such-command"]) == 127
    assert capfd.readouterr().err == "mitm: command not found: mitm-no-such-command\n"


def test_port_in_use(capfd):
    with socket.socket() as sock:
        sock.bind((HOST, 0))
        sock.listen()
        port = sock.getsockname()[1]
        assert cli.main(["-p", str(port), *python("pass")]) == 1

    assert "address already in use" in capfd.readouterr().err.lower()


def test_output_missing_directory(tmp_path, capfd):
    assert cli.main(["-o", str(tmp_path / "missing" / "traffic.jsonl"), *python("pass")]) == 1
    assert capfd.readouterr().err.startswith("mitm: No such file or directory: ")


def test_parser():
    parser = cli.parser()

    # Everything after the options is the command, with or without '--'.
    assert parser.parse_args(["-v", "curl", "-s", "url"]).command == ["curl", "-s", "url"]
    assert parser.parse_args(["--json", "--", "curl", "-v"]).command == ["--", "curl", "-v"]
    assert parser.parse_args([]).command == []


@pytest.mark.parametrize(
    "host, proxy_url",
    [
        ("127.0.0.1", "http://127.0.0.1:9"),
        ("0.0.0.0", "http://127.0.0.1:9"),
        ("::", "http://[::1]:9"),
    ],
)
def test_build_env(host, proxy_url):
    env = cli.build_env(host, 9, Path("/mitm.pem"))
    for key in cli.PROXY_ENV_KEYS:
        assert env[key] == proxy_url
    for key in cli.CERT_ENV_KEYS:
        assert env[key] == "/mitm.pem"
    assert env["NODE_USE_ENV_PROXY"] == "1"


@pytest.mark.asyncio
async def test_serve(ca, capsys):
    task = asyncio.create_task(cli.serve(MITM(port=0, certificate_authority=ca)))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    err = capsys.readouterr().err
    assert f"  ┊ proxy listening on {HOST}:" in err
    assert "--cacert" in err


def test_module():
    result = subprocess.run([sys.executable, "-m", "mitm", "--version"], capture_output=True, text=True, check=True)
    assert result.stdout == f"mitm {mitm.__version__}\n"
