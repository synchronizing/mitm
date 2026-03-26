from __future__ import annotations

import asyncio
import json
import platform
import subprocess
from pathlib import Path

from mitm.intercept import InterceptorBase


class LinuxEBPFInterceptor(InterceptorBase):
    def __init__(self) -> None:
        self._redirector: subprocess.Popen | None = None
        self._proxy_task: asyncio.Task | None = None
        self._child: asyncio.subprocess.Process | None = None
        self._mitm = None

    def _redirector_binary(self) -> Path:
        arch = platform.machine().lower()
        arch_map = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}
        arch_key = arch_map.get(arch, arch)
        path = Path(__file__).parent / "bin" / f"mitm-redirector-linux-{arch_key}"
        if not path.exists():
            raise RuntimeError(
                f"mitm-redirector binary not found: {path}\n"
                "Install a pre-built release or build from source in mitm/intercept/linux/redirector/"
            )
        return path

    async def start(self, host: str, port: int, command: tuple[str, ...]) -> None:
        from mitm.proxy import MITM
        from mitm.extension.middleware import CLILog

        binary = self._redirector_binary()

        self._redirector = subprocess.Popen(
            ["sudo", str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        config = json.dumps(
            {
                "tun_name": "tun0",
                "proxy_port": port,
                "target_process": command[0].split("/")[-1][:15],  # TASK_COMM_LEN max 15 chars
            }
        )
        self._redirector.stdin.write((config + "\n").encode())
        self._redirector.stdin.flush()

        try:
            ready_line = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._redirector.stdout.readline),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            self._redirector.kill()
            raise RuntimeError("mitm-redirector failed to start within 5 seconds")

        status = json.loads(ready_line.decode())
        if status.get("status") != "ready":
            raise RuntimeError(f"mitm-redirector error: {status.get('msg', 'unknown')}")

        self._mitm = MITM(host=host, port=port, middlewares=[CLILog])
        await self._mitm.start()

        # Spawn child process (no proxy env vars — eBPF handles redirection)
        self._child = await asyncio.create_subprocess_exec(*command)

    async def wait(self) -> int:
        if self._child is None:
            return 0
        await self._child.wait()
        return self._child.returncode or 0

    async def stop(self) -> None:
        if self._mitm:
            await self._mitm.stop()
        if self._redirector and self._redirector.poll() is None:
            self._redirector.stdin.write(b'{"action":"stop"}\n')
            self._redirector.stdin.flush()
            try:
                self._redirector.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._redirector.kill()
        self._redirector = None
