import platform
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mitm.intercept import (
    InterceptorBase,
    check_linux_ebpf_requirements,
    check_macos_dylib_requirements,
    detect_platform,
    is_hardened_binary,
)


class Test_CheckLinuxEBPFRequirements:
    def test_old_kernel_fails(self):
        with patch("platform.release", return_value="4.18.0"):
            ok, reason = check_linux_ebpf_requirements()
            assert not ok
            assert "too old" in reason

    def test_missing_btf_fails(self):
        with patch("platform.release", return_value="5.15.0"), patch("pathlib.Path.exists", return_value=False):
            ok, reason = check_linux_ebpf_requirements()
            assert not ok
            assert "BTF" in reason

    def test_missing_sudo_fails(self):
        with (
            patch("platform.release", return_value="5.15.0"),
            patch("pathlib.Path.exists", return_value=True),
            patch("shutil.which", return_value=None),
        ):
            ok, reason = check_linux_ebpf_requirements()
            assert not ok
            assert "sudo" in reason


class Test_CheckMacosDylibRequirements:
    def test_missing_dylib_fails(self):
        with patch("pathlib.Path.exists", return_value=False):
            ok, reason = check_macos_dylib_requirements()
            assert not ok
            assert "libmitmhook.dylib" in reason

    def test_dylib_present_passes(self):
        with patch("pathlib.Path.exists", return_value=True):
            ok, reason = check_macos_dylib_requirements()
            assert ok
            assert reason == ""


class Test_DetectPlatform:
    def test_linux_with_ebpf(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("mitm.intercept.check_linux_ebpf_requirements", return_value=(True, "")),
        ):
            assert detect_platform() == "linux-ebpf"

    def test_linux_without_ebpf_falls_back(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("mitm.intercept.check_linux_ebpf_requirements", return_value=(False, "no sudo")),
        ):
            assert detect_platform() == "env-vars-only"

    def test_macos_with_dylib(self):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("mitm.intercept.check_macos_dylib_requirements", return_value=(True, "")),
        ):
            assert detect_platform() == "macos-dylib"

    def test_windows_falls_back(self):
        with patch("platform.system", return_value="Windows"):
            assert detect_platform() == "env-vars-only"


class Test_IsHardenedBinary:
    def test_non_macos_returns_false(self):
        with patch("platform.system", return_value="Linux"):
            assert is_hardened_binary("/usr/bin/curl") is False

    def test_no_codesign_returns_false(self):
        with patch("platform.system", return_value="Darwin"), patch("shutil.which", return_value=None):
            assert is_hardened_binary("/usr/bin/curl") is False
