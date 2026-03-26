"""
Local capture mode — platform detection and interceptor base.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple


class InterceptorBase(ABC):
    """Abstract base for platform-specific local-capture interceptors."""

    @abstractmethod
    async def start(self, host: str, port: int, command: tuple[str, ...]) -> None:
        """Start interception and run the command."""
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        """Stop interception and clean up."""
        raise NotImplementedError


def detect_platform() -> str:
    """
    Detect the best available interception mechanism.

    Returns:
        "linux-ebpf"   — Linux with BTF + sudo available
        "macos-dylib"  — macOS with hook dylib present
        "env-vars-only" — fallback: only env var injection
    """
    system = platform.system()
    if system == "Linux":
        ok, _ = check_linux_ebpf_requirements()
        return "linux-ebpf" if ok else "env-vars-only"
    elif system == "Darwin":
        ok, _ = check_macos_dylib_requirements()
        return "macos-dylib" if ok else "env-vars-only"
    return "env-vars-only"


def check_linux_ebpf_requirements() -> Tuple[bool, str]:
    """
    Check if Linux eBPF local capture is available.

    Returns:
        (True, "") if all requirements met.
        (False, reason) if something is missing.
    """
    # Check kernel version >= 5.8
    release = platform.release()
    try:
        major, minor = (int(x) for x in release.split(".")[:2])
        if (major, minor) < (5, 8):
            return False, f"Kernel {release} too old (need 5.8+)"
    except (ValueError, IndexError):
        return False, f"Cannot parse kernel version: {release}"

    # Check BTF available
    btf_path = Path("/sys/kernel/btf/vmlinux")
    if not btf_path.exists():
        return False, "BTF not available (/sys/kernel/btf/vmlinux missing)"

    # Check sudo available without password prompt
    if shutil.which("sudo") is None:
        return False, "sudo not found in PATH"
    result = subprocess.run(
        ["sudo", "-n", "true"],
        capture_output=True,
        timeout=5,
    )
    if result.returncode != 0:
        return False, "sudo requires a password (run: sudo -v)"

    # Check mitm-redirector binary present
    arch = platform.machine().lower()
    arch_map = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}
    arch_key = arch_map.get(arch, arch)
    redirector = Path(__file__).parent / "linux" / "bin" / f"mitm-redirector-linux-{arch_key}"
    if not redirector.exists():
        return False, f"mitm-redirector binary not found: {redirector}"

    return True, ""


def check_macos_dylib_requirements() -> Tuple[bool, str]:
    """
    Check if macOS dylib local capture is available.

    Returns:
        (True, "") if dylib present.
        (False, reason) if missing.
    """
    dylib = Path(__file__).parent / "macos" / "lib" / "libmitmhook.dylib"
    if not dylib.exists():
        return False, f"libmitmhook.dylib not found: {dylib}"
    return True, ""


def is_hardened_binary(executable: str) -> bool:
    """
    Check if a macOS binary has the hardened runtime flag set (which strips DYLD env vars).

    Args:
        executable: Path to the binary to check.

    Returns:
        True if hardened runtime is enabled and allow-dyld-environment-variables entitlement is absent.
        False if DYLD injection should work.
    """
    if platform.system() != "Darwin":
        return False

    codesign = shutil.which("codesign")
    if not codesign:
        return False  # Can't check → assume not hardened

    try:
        # Check for hardened runtime flag
        result = subprocess.run(
            [codesign, "-dv", "--verbose=4", executable],
            capture_output=True,
            text=True,
            timeout=5,
        )
        flags_output = result.stderr + result.stdout
        has_hardened = "flags=0x" in flags_output and "runtime" in flags_output.lower()

        if not has_hardened:
            return False  # Not hardened → DYLD works

        # Hardened — check for allow-dyld-environment-variables entitlement
        result2 = subprocess.run(
            [codesign, "-d", "--entitlements", "-", "--xml", executable],
            capture_output=True,
            text=True,
            timeout=5,
        )
        entitlements = result2.stdout + result2.stderr
        if "allow-dyld-environment-variables" in entitlements:
            return False  # Has entitlement → DYLD works even with hardened runtime

        return True  # Hardened + no entitlement → DYLD stripped

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False  # Can't check → assume not hardened
