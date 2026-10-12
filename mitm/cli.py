"""
Command-line interface.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path

import mitm
from mitm.extension.middleware import HTTPLog
from mitm.proxy import MITM

PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")

CA_VARIABLES = (
    "SSL_CERT_FILE",  # OpenSSL-based clients: Python, Ruby, PHP, Go on Linux.
    "REQUESTS_CA_BUNDLE",  # Python requests.
    "CURL_CA_BUNDLE",  # curl, pip.
    "NODE_EXTRA_CA_CERTS",  # Node.js.
    "DENO_CERT",  # Deno.
    "GIT_SSL_CAINFO",  # git.
    "AWS_CA_BUNDLE",  # AWS CLI and SDKs.
)

DESCRIPTION = "Man-in-the-middle proxy for HTTP and HTTPS. Run a command through it to see every request it makes."

EPILOG = """\
examples:
  mitm -- curl https://example.com          one line per request
  mitm -v -- python app.py                  include headers and bodies
  mitm --json -o traffic.jsonl -- npm ci    save every exchange as JSON Lines
  mitm                                      standalone proxy on 127.0.0.1:8888

The command runs with HTTP(S)_PROXY and CA certificate variables pointing at the
proxy, so most tools are captured without configuration. Traffic goes to stderr
(or FILE); the command's own output is untouched, and its exit code is returned.
"""


def main(argv: list[str] | None = None) -> int:
    """
    Runs the CLI and returns its exit code.
    """
    args = parser().parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    port = args.port if args.port is not None else 0 if command else 8888

    with contextlib.ExitStack() as stack:
        try:
            output = stack.enter_context(open(args.output, "w", encoding="utf-8")) if args.output else None
            log = HTTPLog(output, verbose=args.verbose, json=args.json, max_body=args.max_body or None)
            proxy = MITM(host=args.host, port=port, middlewares=[log])
            return asyncio.run(run(proxy, command, log) if command else serve(proxy))
        except OSError as err:
            print(
                f"mitm: {err.strerror or err}: {err.filename}" if err.filename else f"mitm: {err.strerror or err}",
                file=sys.stderr,
            )
            return 1
        except KeyboardInterrupt:
            return 130


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mitm",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command to run through the proxy")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: %(default)s)")
    parser.add_argument(
        "-p", "--port", type=int, help="port to listen on (default: 8888, or any free port with a command)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="include headers and bodies")
    parser.add_argument("--json", action="store_true", help="write one JSON object per exchange (JSON Lines)")
    parser.add_argument("-o", "--output", metavar="FILE", help="write traffic to FILE instead of stderr")
    parser.add_argument(
        "--max-body",
        type=int,
        default=4096,
        metavar="BYTES",
        help="truncate bodies after BYTES, or 0 for no limit (default: %(default)s)",
    )
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {mitm.__version__}")
    return parser


async def run(proxy: MITM, command: list[str], log: HTTPLog) -> int:
    """
    Runs `command` with its traffic routed through `proxy`, and returns its exit code.
    """
    async with proxy:
        env = environment(proxy.host, proxy.port, mitm.__data__ / "mitm.pem")
        try:
            child = await asyncio.create_subprocess_exec(*command, env=env)
        except FileNotFoundError:
            print(f"mitm: command not found: {command[0]}", file=sys.stderr)
            return 127
        except PermissionError:
            print(f"mitm: permission denied: {command[0]}", file=sys.stderr)
            return 126

        # Ctrl-C reaches the command directly, as it shares our process group. Other
        # termination signals are forwarded. Either way, mitm exits when the command does.
        loop = asyncio.get_running_loop()
        with contextlib.suppress(NotImplementedError):  # Not supported on Windows.
            loop.add_signal_handler(signal.SIGINT, lambda: None)
            for signum in (signal.SIGTERM, signal.SIGHUP):
                loop.add_signal_handler(signum, child.send_signal, signum)

        code = await child.wait()

    if log.count == 0:
        note("no traffic captured; if the command made HTTP requests, it ignores HTTP(S)_PROXY")
    return 128 - code if code < 0 else code


async def serve(proxy: MITM) -> int:
    """
    Runs `proxy` until interrupted.
    """
    async with proxy:
        url, ca = f"http://{proxy.host}:{proxy.port}", mitm.__data__ / "mitm.pem"
        note(f"mitm {mitm.__version__} listening on {url}")
        note(f"CA certificate: {ca} (or open {url}/ to install it)")
        note(f"try: curl --proxy {url} --cacert '{ca}' https://example.com")
        await proxy.server.serve_forever()
    return 0


def environment(host: str, port: int, ca: Path) -> dict[str, str]:
    """
    Returns a copy of the environment that routes HTTP(S) traffic through the proxy,
    and makes common tools trust its CA certificate.
    """
    host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    url = f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"

    env = dict(os.environ)
    env.update(dict.fromkeys(PROXY_VARIABLES, url))
    env.update(dict.fromkeys(CA_VARIABLES, str(ca)))
    env["NODE_USE_ENV_PROXY"] = "1"  # Node.js 24+ ignores proxy variables without it.
    return env


def note(message: str):
    """
    Writes a status message to stderr.
    """
    color = sys.stderr.isatty() and not os.environ.get("NO_COLOR")
    print(f"\x1b[2m{HTTPLog.gutter}{message}\x1b[0m" if color else f"{HTTPLog.gutter}{message}", file=sys.stderr)
