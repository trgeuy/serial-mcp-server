"""serial-watch -- watch the serial MCP server's TCP mirror in a terminal window.

Installed with the package as the ``serial-watch`` command (``uv tool install`` puts it next to ``serial_mcp``).
Run it in a second window while an agent drives the device through the server; it shows every byte the device
sends, including the replies to what the agent types.

Usage::

    serial-watch                 watch localhost:2424 (the server's default TCP mirror port)
    serial-watch PORT            watch localhost:PORT
    serial-watch HOST PORT       watch a mirror on another computer

Start the server with ``SERIAL_MCP_MIRROR=ro`` (or ``rw``) and ``SERIAL_MCP_MIRROR_TRANSPORT=tcp``. Press Ctrl-C to
stop watching.

It only watches: it does not send what you type. To type into the device through a read-write mirror, use a full
terminal program instead.

What it does:
  - If the mirror is not there yet, it waits and tries again every second.
  - When it connects, it shows the bytes as they arrive, until the connection ends.
  - When the connection ends (the agent closed the port, or the server stopped), it waits for the mirror to come
    back and connects again.

It makes only one connection at a time and never "tests" the port with a second connection. The server's TCP mirror
accepts one watcher at a time: a second watcher gets the line "another client is already connected", and its
connection ends. serial-watch then tries again every second. If you see that line repeat, close the other watcher.

The bytes are shown as they arrive, so do not turn on telnet negotiation on the server
(``SERIAL_MCP_MIRROR_TCP_TELNET``): those bytes show as junk here.

This is the Python, any-OS version of the ``mirror-watch.sh`` / ``mirror-watch.ps1`` scripts that this fork wrote
first (altairsim ships its own ``tools/mirror-watch.sh`` for its machine mirror; that one is unchanged). It prints
the same messages.
"""

from __future__ import annotations

import os
import socket
import sys
import time

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 2424   # the server's default SERIAL_MCP_MIRROR_TCP_PORT
RETRY_DELAY = 1.0     # seconds between tries while the mirror is not there
CONNECT_TIMEOUT = 3.0 # seconds one connection try may take
RECV_POLL = 0.5       # seconds one read may block. On Windows, Ctrl-C does not interrupt a blocked socket call:
                      # it takes effect only when the call returns. Short reads let Ctrl-C stop a silent device.
USAGE = "Usage: serial-watch [port | host port]"


def _out(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _say(text: str) -> None:
    _out(f"\n[{time.strftime('%H:%M:%S')}] {text}\n")


def _enable_windows_vt() -> None:
    """Let the classic Windows console interpret the device's escape sequences (Windows Terminal already does)."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)                      # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass   # not a console (e.g. redirected): nothing to enable


def parse_args(argv: list[str]) -> tuple[str, int]:
    """[] -> localhost:2424; [port] -> localhost:port; [host, port]. Raises ValueError with a message."""
    if len(argv) >= 2:
        host, port_text = argv[0], argv[1]
    elif len(argv) == 1:
        host, port_text = DEFAULT_HOST, argv[0]
    else:
        host, port_text = DEFAULT_HOST, str(DEFAULT_PORT)
    if not port_text.isdigit():
        raise ValueError(f'serial-watch: "{port_text}" is not a port number.')
    return host, int(port_text)


def watch(host: str, port: int) -> None:
    """Watch host:port until Ctrl-C (KeyboardInterrupt is left to the caller)."""
    _say(f"Watching {host}:{port}. Press Ctrl-C to stop.")
    out = sys.stdout.buffer
    waiting_shown = False
    while True:
        try:
            sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
        except OSError:
            if not waiting_shown:
                _say(f"Nothing on {host}:{port} yet. Waiting...")
                waiting_shown = True
            else:
                _out(".")
        else:
            with sock:
                sock.settimeout(RECV_POLL)
                _say(f"Connected to {host}:{port}.")
                while True:
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
                        continue   # the device is quiet: keep watching
                    except OSError:
                        break
                    if not data:
                        break
                    out.write(data)
                    out.flush()
            _say("The connection ended. Waiting for the mirror to come back...")
            waiting_shown = True
        time.sleep(RETRY_DELAY)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(USAGE)
        print("Watch the serial MCP server's TCP mirror (default localhost:2424). Ctrl-C stops.")
        return 0
    try:
        host, port = parse_args(argv)
    except ValueError as e:
        print(e, file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 1
    _enable_windows_vt()
    try:
        watch(host, port)
    except KeyboardInterrupt:
        _out("\n")
        _say("Stopped watching.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
