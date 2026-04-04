"""
Command-line interface.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import click

from mitm import __data__
from mitm.extension.middleware import CLILog
from mitm.proxy import MITM

PROXY_ENV_KEYS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
]

CERT_ENV_KEYS = [
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS",
    "CURL_CA_BUNDLE",
]


@click.command(context_settings={"ignore_unknown_options": True})
@click.option("--host", default="127.0.0.1", show_default=True, help="Host to listen on.")
@click.option("-p", "--port", default=8888, show_default=True, type=int, help="Port to listen on.")
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
def main(host: str, port: int, command: tuple[str, ...]):
    """
    Man-in-the-middle proxy.

    Run standalone as a proxy server, or wrap a COMMAND to capture its traffic.

    \b
    Examples:
        mitm                              Start proxy on default port.
        mitm -p 9999                      Start proxy on port 9999.
        mitm -- curl https://example.com  Capture curl's traffic.
        mitm -- python my_script.py       Capture a script's traffic.
    """
    logging.getLogger("mitm").setLevel(logging.CRITICAL)

    if command:
        code = asyncio.run(wrap_local(host, port, command))
        sys.exit(code)
    else:
        MITM(host=host, port=port, middlewares=[CLILog]).run()


async def wrap(host: str, port: int, command: tuple[str, ...]) -> int:
    """
    Start the proxy, run a command with traffic routed through it, then shut down.

    Args:
        host: Proxy bind host.
        port: Proxy bind port.
        command: The command and its arguments.

    Returns:
        The child process exit code.
    """
    async with MITM(host=host, port=port, middlewares=[CLILog]):
        env = build_env(host, port)

        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                env=env,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            await proc.wait()
            return proc.returncode or 0
        except FileNotFoundError:
            click.echo(f"mitm: command not found: {command[0]}", err=True)
            return 127


async def wrap_local(host: str, port: int, command: tuple[str, ...]) -> int:
    """
    Start the proxy in local capture mode, run command with all TCP intercepted.

    Falls back to env-var mode if eBPF/dylib not available.

    Args:
        host: Proxy bind host.
        port: Proxy bind port.
        command: The command and its arguments.

    Returns:
        The child process exit code.
    """
    from mitm.intercept import detect_platform

    platform_mode = detect_platform()

    if platform_mode == "linux-ebpf":
        from mitm.intercept.linux.ebpf import LinuxEBPFInterceptor

        interceptor = LinuxEBPFInterceptor()
        await interceptor.start(host, port, command)
        return await interceptor.wait()

    elif platform_mode == "macos-dylib":
        from mitm.intercept.macos.dylib import MacOSDylibInterceptor

        interceptor = MacOSDylibInterceptor()
        await interceptor.start(host, port, command)
        return await interceptor.wait()

    else:
        return await wrap(host, port, command)


def build_env(host: str, port: int) -> dict[str, str]:
    """
    Build an environment dict that routes traffic through the proxy.

    Args:
        host: Proxy host.
        port: Proxy port.

    Returns:
        A copy of the current environment with proxy and CA cert variables set.
    """
    env = os.environ.copy()

    proxy_url = f"http://{host}:{port}"
    for key in PROXY_ENV_KEYS:
        env[key] = proxy_url

    cert_path = str(__data__ / "mitm.crt")
    for key in CERT_ENV_KEYS:
        env[key] = cert_path

    return env
