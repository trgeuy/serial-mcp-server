"""On Windows only the PTY mirror transport is impossible; the TCP mirror must stay on (0.2.7). Before, any
SERIAL_MCP_MIRROR value was turned off on Windows, so the TCP mirror never started there."""

import os
import subprocess
import sys

import pytest

from serial_mcp_server.helpers import mirror_unsupported


@pytest.mark.parametrize("mode,transport,is_windows,expected", [
    ("ro", "tcp", True, False),    # the case that was broken: TCP mirror on Windows
    ("rw", "tcp", True, False),
    ("ro", "pty", True, True),     # no pseudo-terminal on Windows
    ("off", "pty", True, False),
    ("ro", "pty", False, False),
    ("ro", "tcp", False, False),
])
def test_mirror_unsupported(mode, transport, is_windows, expected):
    assert mirror_unsupported(mode, transport, is_windows) is expected


def test_tcp_mirror_mode_survives_import():
    env = {k: v for k, v in os.environ.items() if not k.startswith("SERIAL_MCP_MIRROR")}
    env.update(SERIAL_MCP_MIRROR="ro", SERIAL_MCP_MIRROR_TRANSPORT="tcp")
    out = subprocess.run([sys.executable, "-c",
                          "from serial_mcp_server.helpers import MIRROR_PTY, MIRROR_TRANSPORT; "
                          "print(MIRROR_PTY, MIRROR_TRANSPORT)"],
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == "ro tcp"
