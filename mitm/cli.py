"""
Command-line interface.
"""

import argparse
import asyncio
import contextlib
import os
import signal
import sys
from pathlib import Path
from typing import Dict, List, Optional

import mitm
from mitm.extension.middleware import HTTPLog
from mitm.proxy import MITM

PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
]

CERT_ENV_KEYS = [
    "SSL_CERT_FILE",  # Python, Ruby, PHP, and Go (Linux).
    "REQUESTS_CA_BUNDLE",  # Python's requests.
    "CURL_CA_BUNDLE",  # curl, and pip.
    "NODE_EXTRA_CA_CERTS",  # Node.js.
    "DENO_CERT",  # Deno.
    "GIT_SSL_CAINFO",  # git.
    "AWS_CA_BUNDLE",  # AWS CLI, and AWS SDKs.
]

DESCRIPTION = """\
Man-in-the-middle proxy.

Run standalone as a proxy server, or wrap a COMMAND to capture its traffic.
"""

EXAMPLES = """\
Examples:
    mitm                                      Start proxy on default port.
    mitm -p 9999                              Start proxy on port 9999.
    mitm -- curl https://example.com          Capture curl's traffic.
    mitm -- python my_script.py               Capture a script's traffic.
    mitm -v -- python my_script.py            Capture a script's traffic, with headers and bodies.
    mitm --json -o traffic.jsonl -- npm ci    Capture npm's traffic as JSON.
"""


def main(argv: Optional[List[str]] = None) -> int:
    """
    Man-in-the-middle proxy.

    Args:
        argv: The command-line arguments. Defaults to `sys.argv`.

    Returns:
        The exit code. When wrapping a command, this is the command's exit code.
    """
    args = parser().parse_args(argv)

    # Everything after '--' is the command to wrap.
    command = args.command
    if command[:1] == ["--"]:
        command = command[1:]

    # Standalone proxies default to port 8888. Wrapped commands use any free port, so
    # multiple commands can be wrapped at the same time.
    port = args.port
    if port is None:
        port = 0 if command else 8888

    with contextlib.ExitStack() as stack:
        try:
            output = stack.enter_context(open(args.output, "w", encoding="utf-8")) if args.output else None
            log = HTTPLog(output, verbose=args.verbose, json=args.json, max_body=args.max_body or None)
            proxy = MITM(host=args.host, port=port, middlewares=[log])

            if command:
                return asyncio.run(wrap(proxy, command, log))
            return asyncio.run(serve(proxy))

        # Unable to listen on the port, or to open the output file.
        except OSError as err:
            message = err.strerror if err.strerror else str(err)
            if err.filename:
                message += f": {err.filename}"
            print(f"mitm: {message}", file=sys.stderr)
            return 1

        except KeyboardInterrupt:
            return 130


def parser() -> argparse.ArgumentParser:
    """
    Builds the command-line argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="mitm",
        description=DESCRIPTION,
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to wrap.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to listen on. Defaults to %(default)s.",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        help="Port to listen on. Defaults to 8888, or to any free port when wrapping a command.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log the headers and bodies too.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Log each request as a JSON object, one per line.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Log to a file instead of stderr.",
    )
    parser.add_argument(
        "--max-body",
        type=int,
        default=4096,
        metavar="BYTES",
        help="Max size of each body that is logged. Use 0 for no limit. Defaults to %(default)s.",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {mitm.__version__}",
    )
    return parser


async def wrap(proxy: MITM, command: List[str], log: HTTPLog) -> int:
    """
    Start the proxy, run a command with traffic routed through it, then shut down.

    Args:
        proxy: The proxy.
        command: The command and its arguments.
        log: The middleware logging the traffic.

    Returns:
        The child process exit code.
    """
    async with proxy:
        env = build_env(proxy.host, proxy.port, mitm.__data__ / "mitm.pem")

        try:
            proc = await asyncio.create_subprocess_exec(*command, env=env)
        except FileNotFoundError:
            print(f"mitm: command not found: {command[0]}", file=sys.stderr)
            return 127
        except PermissionError:
            print(f"mitm: permission denied: {command[0]}", file=sys.stderr)
            return 126

        # Ctrl-C is sent to the child process by the terminal, so 'mitm' ignores it and
        # waits for the child to exit. Other signals are sent to the child process.
        # Note that Windows does not support signal handlers.
        loop = asyncio.get_running_loop()
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(signal.SIGINT, lambda: None)
            for signum in (signal.SIGTERM, signal.SIGHUP):
                loop.add_signal_handler(signum, proc.send_signal, signum)

        returncode = await proc.wait()

    if log.count == 0:
        note("no traffic captured (the command might not respect HTTP_PROXY or HTTPS_PROXY)")

    # Child processes killed by a signal exit with 128 + the signal number, like in a shell.
    if returncode < 0:
        return 128 - returncode
    return returncode


async def serve(proxy: MITM) -> int:
    """
    Start the proxy, and serve until interrupted.

    Args:
        proxy: The proxy.

    Returns:
        The exit code.
    """
    async with proxy:
        url = f"http://{proxy.host}:{proxy.port}"
        cert_path = mitm.__data__ / "mitm.pem"

        note(f"proxy listening on {proxy.host}:{proxy.port}")
        note(f"CA certificate is stored in {cert_path}")
        note(f"browse to {url} to download and install it")
        note(f"example: curl --proxy {url} --cacert '{cert_path}' https://example.com")

        await proxy.server.serve_forever()

    return 0


def build_env(host: str, port: int, cert_path: Path) -> Dict[str, str]:
    """
    Build an environment dict that routes traffic through the proxy.

    Args:
        host: Proxy host.
        port: Proxy port.
        cert_path: Path to the CA certificate.

    Returns:
        A copy of the current environment with proxy and CA cert variables set.
    """

    # Proxies listening on all interfaces are reached through the loopback interface.
    if host == "0.0.0.0":
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"

    # IPv6 addresses must be wrapped in brackets.
    proxy_url = f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"

    env = os.environ.copy()
    for key in PROXY_ENV_KEYS:
        env[key] = proxy_url
    for key in CERT_ENV_KEYS:
        env[key] = str(cert_path)

    # Node.js (24+) only respects the proxy variables if this is set.
    env["NODE_USE_ENV_PROXY"] = "1"

    return env


def note(message: str):
    """
    Writes a message to stderr, with a dim gutter if stderr is a terminal.

    Args:
        message: The message.
    """
    if sys.stderr.isatty() and not os.environ.get("NO_COLOR"):
        print(f"\x1b[2m{HTTPLog.gutter}{message}\x1b[0m", file=sys.stderr)
    else:
        print(f"{HTTPLog.gutter}{message}", file=sys.stderr)
