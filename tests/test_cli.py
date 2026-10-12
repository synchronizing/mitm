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


def python(code: str) -> list[str]:
    return ["--", sys.executable, "-c", code]


def fetch(url: str) -> list[str]:
    return python(f"import urllib.request; print(urllib.request.urlopen({url!r}).read().decode())")


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for name in ("NO_PROXY", "no_proxy", "NO_COLOR"):
        monkeypatch.delenv(name, raising=False)


def test_http(origin, capfd):
    url = f"http://127.0.0.1:{origin.port}/hello"
    assert cli.main(fetch(url)) == 0
    out, err = capfd.readouterr()
    assert out == "hello\n"
    assert err.startswith(f"  ┊ GET {url} → 200 OK (text/plain, 5 B, ")


def test_https_json(tls_origin, ca_file, tmp_path, monkeypatch, capfd):
    # The proxy must trust the local origin; the command trusts the proxy via SSL_CERT_FILE.
    default_context = ssl.create_default_context
    monkeypatch.setattr(ssl, "create_default_context", lambda: default_context(cafile=ca_file))

    output = tmp_path / "traffic.jsonl"
    url = f"https://localhost:{tls_origin.port}/hello"
    assert cli.main(["--json", "-o", str(output), *fetch(url)]) == 0
    assert capfd.readouterr() == ("hello\n", "")

    [record] = [json.loads(line) for line in output.read_text().splitlines()]
    assert record["request"]["url"] == url
    assert record["response"]["body"] == "hello"


def test_verbose(origin, capfd):
    assert cli.main(["-v", "--max-body", "3", *fetch(f"http://127.0.0.1:{origin.port}/hello")]) == 0
    err = capfd.readouterr().err
    assert "  ┊ Host: 127.0.0.1" in err
    assert "  ┊ hel\n  ┊ … truncated (5 B received)" in err


def test_exit_code_and_no_traffic(capfd):
    assert cli.main(python("raise SystemExit(3)")) == 3
    assert "no traffic captured" in capfd.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_killed_by_signal():
    assert cli.main(python("import os, signal; os.kill(os.getpid(), signal.SIGTERM)")) == 128 + 15


def test_command_not_found(capfd):
    assert cli.main(["--", "mitm-no-such-command"]) == 127
    assert capfd.readouterr().err == "mitm: command not found: mitm-no-such-command\n"


def test_port_in_use(capfd):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        assert cli.main(["-p", str(port), *python("pass")]) == 1
    assert "address already in use" in capfd.readouterr().err.lower()


def test_unwritable_output(tmp_path, capfd):
    assert cli.main(["-o", str(tmp_path / "missing" / "out.jsonl"), *python("pass")]) == 1
    assert capfd.readouterr().err.startswith("mitm: No such file or directory: ")


def test_arguments():
    parser = cli.parser()
    assert parser.parse_args(["-v", "curl", "-s", "url"]).command == ["curl", "-s", "url"]
    assert parser.parse_args(["--json", "--", "curl", "-v"]).command == ["--", "curl", "-v"]
    assert parser.parse_args([]).command == []


@pytest.mark.parametrize(
    ("host", "url"),
    [("127.0.0.1", "http://127.0.0.1:9"), ("0.0.0.0", "http://127.0.0.1:9"), ("::", "http://[::1]:9")],
)
def test_environment(host, url):
    env = cli.environment(host, 9, Path("/ca.pem"))
    assert all(env[name] == url for name in cli.PROXY_VARIABLES)
    assert all(env[name] == "/ca.pem" for name in cli.CA_VARIABLES)
    assert env["NODE_USE_ENV_PROXY"] == "1"


async def test_serve(ca, capsys):
    task = asyncio.create_task(cli.serve(MITM(port=0, certificate_authority=ca)))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    err = capsys.readouterr().err
    assert f"  ┊ mitm {mitm.__version__} listening on http://127.0.0.1:" in err
    assert "--cacert" in err


def test_module_entry_point():
    result = subprocess.run([sys.executable, "-m", "mitm", "--version"], capture_output=True, text=True, check=True)
    assert result.stdout == f"mitm {mitm.__version__}\n"
