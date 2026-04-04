from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click

from mitm.intercept import InterceptorBase


class MacOSDylibInterceptor(InterceptorBase):
    def __init__(self) -> None:
        self._child: asyncio.subprocess.Process | None = None
        self._mitm = None

    def _dylib_path(self) -> Path:
        path = Path(__file__).parent / "lib" / "libmitmhook.dylib"
        if not path.exists():
            raise RuntimeError(f"libmitmhook.dylib not found: {path}")
        return path

    async def start(self, host: str, port: int, command: tuple[str, ...]) -> None:
        from mitm.proxy import MITM
        from mitm.extension.middleware import CLILog
        from mitm.intercept import is_hardened_binary

        dylib = self._dylib_path()
        executable = command[0]

        try:
            hardened = is_hardened_binary(executable)
        except Exception:
            hardened = False

        if hardened:
            click.echo(
                f"[mitm] warning: {executable} has hardened runtime — DYLD injection stripped.\n"
                "       Falling back to env vars (coverage may be incomplete).",
                err=True,
            )

        self._mitm = MITM(host=host, port=port, middlewares=[CLILog])
        await self._mitm.start()

        env = os.environ.copy()
        env["MITM_LOCAL_PORT"] = str(port)

        if not hardened:
            env["DYLD_INSERT_LIBRARIES"] = str(dylib)
            env["DYLD_FORCE_FLAT_NAMESPACE"] = "1"
        else:
            proxy_url = f"http://{host}:{port}"
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
                env[key] = proxy_url

        self._child = await asyncio.create_subprocess_exec(
            *command,
            env=env,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )

        if not hardened:
            # After exec(), MITM_HOOK_LOADED set by the dylib constructor lives in the child's
            # address space only — the parent cannot observe it. Best-effort: give the child
            # time to boot, then rely on exit-code checks in wait().
            await asyncio.sleep(1.0)

    async def wait(self) -> int:
        if self._child is None:
            return 0
        await self._child.wait()
        return self._child.returncode or 0

    async def stop(self) -> None:
        if self._mitm:
            await self._mitm.stop()
        self._mitm = None
