"""The paced.* tools are ON by default (0.2.5); SERIAL_MCP_PACED=0 turns them off. PACED_ENABLED is read at import,
so each case runs in a fresh interpreter."""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize("value,expected", [(None, "True"), ("1", "True"), ("0", "False"), ("false", "False"),
                                            ("no", "False"), ("", "False")])
def test_paced_enabled(value, expected):
    env = {k: v for k, v in os.environ.items() if k != "SERIAL_MCP_PACED"}
    if value is not None:
        env["SERIAL_MCP_PACED"] = value
    out = subprocess.run([sys.executable, "-c", "from serial_mcp_server.helpers import PACED_ENABLED; print(PACED_ENABLED)"],
                         env=env, capture_output=True, text=True, check=True).stdout.strip()
    assert out == expected
