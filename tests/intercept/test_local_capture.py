import platform
import sys

import pytest
from click.testing import CliRunner

from mitm.cli import main


class Test_CLIHelpText:
    def test_help_shows_host_and_port(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output

    def test_help_shows_command_example(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "curl" in result.output


@pytest.mark.skipif(platform.system() != "Linux", reason="eBPF local capture tests require Linux")
@pytest.mark.ebpf
class Test_LinuxLocalCapture:
    def test_detect_platform_returns_linux_or_fallback(self):
        from mitm.intercept import detect_platform

        result = detect_platform()
        assert result in ("linux-ebpf", "env-vars-only")

    @pytest.mark.asyncio
    async def test_wrap_local_fallback_runs_command(self):
        from mitm.cli import wrap_local
        from unittest.mock import patch

        with patch("mitm.intercept.detect_platform", return_value="env-vars-only"):
            with patch("mitm.cli.wrap") as mock_wrap:
                mock_wrap.return_value = 0
                result = await wrap_local("127.0.0.1", 18910, ("echo", "hello"))
                assert mock_wrap.called


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS dylib tests require macOS")
@pytest.mark.macos_dylib
class Test_MacOSLocalCapture:
    def test_detect_platform_returns_macos_or_fallback(self):
        from mitm.intercept import detect_platform

        result = detect_platform()
        assert result in ("macos-dylib", "env-vars-only")

    def test_dylib_exists_in_package(self):
        from pathlib import Path

        dylib = Path(__file__).parent.parent.parent / "mitm" / "intercept" / "macos" / "lib" / "libmitmhook.dylib"
        assert dylib.exists(), f"libmitmhook.dylib not found at {dylib}"

    @pytest.mark.asyncio
    async def test_wrap_local_fallback_runs_command(self):
        from mitm.cli import wrap_local
        from unittest.mock import patch

        with patch("mitm.intercept.detect_platform", return_value="env-vars-only"):
            with patch("mitm.cli.wrap") as mock_wrap:
                mock_wrap.return_value = 0
                result = await wrap_local("127.0.0.1", 18911, ("echo", "hello"))
                assert mock_wrap.called
