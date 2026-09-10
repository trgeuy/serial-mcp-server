"""Serial port buffering and mirroring (PTY or TCP).

Provides:
- ``SerialBuffer``: thread-safe byte buffer with blocking reads
- ``ReaderThread``: background thread that reads from serial into buffer;
  also owns the generic exclusive-forwarding pause/resume mechanism, even
  though only a mirror subclass ever has anything to forward
- ``MirrorSession``: extends ReaderThread with PTY tee (Unix only)
- ``TcpMirrorSession``: extends ReaderThread with a TCP socket tee
  (cross-platform -- sockets work everywhere, unlike PTYs)
- ``create_reader``: factory that picks the right reader based on config
"""

from __future__ import annotations

import logging
import os
import select
import socket
import sys
import threading
import time
from typing import Any

logger = logging.getLogger("serial_mcp_server")

_IS_UNIX = sys.platform != "win32"

if _IS_UNIX:
    import fcntl
    import termios
    import tty

# Exclusive-pause bounds. A pause always auto-expires -- a crashed or
# erroring caller must never lock out a human attached to the mirror.
_EXCLUSIVE_DEFAULT_MS = 5_000
_EXCLUSIVE_MAX_MS = 30_000
_EXCLUSIVE_MIN_MS = 100


# ---------------------------------------------------------------------------
# SerialBuffer — thread-safe byte buffer
# ---------------------------------------------------------------------------


class SerialBuffer:
    """Thread-safe byte buffer with blocking reads.

    The background reader writes into this buffer. MCP tool handlers
    read from it.
    """

    def __init__(self, max_size: int = 1_048_576) -> None:
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._max_size = max_size

    def write(self, data: bytes) -> None:
        """Append data to the buffer and wake any waiting readers."""
        if not data:
            return
        with self._cond:
            self._buf.extend(data)
            # Trim from the front if we exceed max size (drop oldest data).
            if len(self._buf) > self._max_size:
                excess = len(self._buf) - self._max_size
                del self._buf[:excess]
            self._cond.notify_all()

    def read(self, nbytes: int, timeout: float) -> bytes:
        """Read up to *nbytes*, blocking until data arrives or *timeout* expires."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._buf:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return b""
                self._cond.wait(timeout=remaining)
            n = min(nbytes, len(self._buf))
            result = bytes(self._buf[:n])
            del self._buf[:n]
            return result

    def read_until(self, delimiter: bytes, max_bytes: int, timeout: float) -> bytes:
        """Read until *delimiter* is found, *max_bytes* reached, or *timeout* expires."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                idx = self._buf.find(delimiter)
                if idx != -1:
                    end = min(idx + len(delimiter), max_bytes)
                    result = bytes(self._buf[:end])
                    del self._buf[:end]
                    return result
                if len(self._buf) >= max_bytes:
                    result = bytes(self._buf[:max_bytes])
                    del self._buf[:max_bytes]
                    return result
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # Return whatever we have.
                    n = min(len(self._buf), max_bytes)
                    result = bytes(self._buf[:n])
                    del self._buf[:n]
                    return result
                self._cond.wait(timeout=remaining)

    def clear(self) -> None:
        """Discard all buffered data."""
        with self._lock:
            self._buf.clear()

    @property
    def available(self) -> int:
        """Number of bytes currently in the buffer."""
        with self._lock:
            return len(self._buf)


# ---------------------------------------------------------------------------
# ReaderThread — background serial reader (cross-platform)
# ---------------------------------------------------------------------------


class ReaderThread:
    """Background thread that continuously reads from a serial port into a buffer."""

    def __init__(self, ser: Any, buffer: SerialBuffer) -> None:
        self.ser = ser
        self.buffer = buffer
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.write_lock = threading.Lock()

        # Exclusive-forwarding pause state. Tracked generically here even
        # though a plain ReaderThread never calls _forward_or_drop (nothing
        # external to forward from) -- only a mirror subclass's rw mode
        # actually observes any effect. Harmless to track anyway, and it
        # means callers never need an isinstance(MirrorSession) check.
        self._pause_lock = threading.Lock()
        self._pause_depth = 0
        self._pause_deadline: float | None = None
        self.dropped_while_paused = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True, name="serial-reader")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    _MAX_CONSECUTIVE_ERRORS = 10

    def _run(self) -> None:
        errors = 0
        while not self._stop.is_set():
            try:
                waiting = self.ser.in_waiting
                if waiting:
                    data = self.ser.read(waiting)
                    if data:
                        self._on_data(data)
                else:
                    # Block for up to 1 byte with the serial port's own timeout.
                    data = self.ser.read(1)
                    if data:
                        self._on_data(data)
                errors = 0
            except Exception:
                if self._stop.is_set():
                    break
                errors += 1
                if errors >= self._MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        "Reader thread for %s stopping after %d consecutive errors.", self.ser.port, errors
                    )
                    break
                time.sleep(0.1)

    def _on_data(self, data: bytes) -> None:
        """Called when data arrives from the serial port. Override to tee."""
        self.buffer.write(data)

    def mirror_info(self) -> dict[str, Any] | None:
        """Return mirror metadata, or None if this is a plain reader."""
        return None

    # -- Exclusive-forwarding controls -------------------------------------
    # Generic on this base class; only a mirror subclass's rw _run() loop
    # ever calls _forward_or_drop, so these have zero observable effect
    # here, but are always safe and depth-accurate to call regardless.

    def pause_forwarding(self, timeout_ms: float | None = None) -> float:
        """Pause external-to-serial forwarding. Returns the applied timeout in ms.

        Depth-counted so nested begin/end pairs compose safely. Always
        auto-expires: a caller that never resumes (crash, error, forgotten
        call) cannot lock out a human attached to the mirror for longer
        than *timeout_ms* (clamped to [100, 30000], default 5000).
        """
        if timeout_ms is None:
            timeout_ms = _EXCLUSIVE_DEFAULT_MS
        timeout_ms = max(_EXCLUSIVE_MIN_MS, min(float(timeout_ms), _EXCLUSIVE_MAX_MS))
        with self._pause_lock:
            self._pause_depth += 1
            self._pause_deadline = time.monotonic() + timeout_ms / 1000.0
        return timeout_ms

    def resume_forwarding(self) -> None:
        """Resume forwarding. Safe to call even if not paused (no-op)."""
        with self._pause_lock:
            if self._pause_depth > 0:
                self._pause_depth -= 1
            if self._pause_depth == 0:
                self._pause_deadline = None

    @property
    def is_forwarding_paused(self) -> bool:
        with self._pause_lock:
            return self._pause_depth > 0

    @property
    def pause_depth(self) -> int:
        with self._pause_lock:
            return self._pause_depth

    def _check_pause_expired(self) -> None:
        """Force-clear an expired pause. Called from a mirror's reader loop only."""
        with self._pause_lock:
            if (
                self._pause_depth > 0
                and self._pause_deadline is not None
                and time.monotonic() > self._pause_deadline
            ):
                logger.warning(
                    "Exclusive forwarding pause on %s expired without resume_forwarding() "
                    "being called (depth was %d) -- auto-resuming.",
                    self.ser.port,
                    self._pause_depth,
                )
                self._pause_depth = 0
                self._pause_deadline = None

    def _forward_or_drop(self, data: bytes) -> None:
        """Forward *data* (from an external mirror client) to the serial port.

        Drops and counts it instead if forwarding is currently paused. Shared
        by every mirror transport's rw-mode branch -- the decision is the
        same regardless of whether the bytes came from a PTY or a socket.
        """
        if self.is_forwarding_paused:
            self.dropped_while_paused += len(data)
            return
        with self.write_lock:
            self.ser.write(data)


# ---------------------------------------------------------------------------
# MirrorSession — PTY tee on top of ReaderThread (Unix only)
# ---------------------------------------------------------------------------


class MirrorSession(ReaderThread):
    """Background reader that also tees serial data to a PTY.

    In rw mode, data written to the PTY slave by an external tool
    is forwarded to the real serial port.
    """

    def __init__(
        self,
        ser: Any,
        buffer: SerialBuffer,
        mode: str,
        link_path: str | None = None,
    ) -> None:
        super().__init__(ser, buffer)
        self.mode = mode  # "ro" or "rw"
        self.link_path = link_path

        # Create PTY pair.
        self._master_fd, self._slave_fd = os.openpty()

        # Non-blocking master so writes don't stall the reader thread
        # when nothing is connected to the slave.
        flags = fcntl.fcntl(self._master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self._master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Put slave in raw mode and set baud rate.
        try:
            tty.setraw(self._slave_fd)
            attrs = termios.tcgetattr(self._slave_fd)
            baud = getattr(termios, f"B{ser.baudrate}", termios.B115200)
            attrs[4] = baud  # ispeed
            attrs[5] = baud  # ospeed
            termios.tcsetattr(self._slave_fd, termios.TCSANOW, attrs)
        except Exception:
            pass  # Best-effort baud config.

        self.pty_slave_path: str = os.ttyname(self._slave_fd)
        self._mirror_index: int | None = None  # Set by create_reader if link is used.

        # Create symlink if requested.
        self._link_created = False
        if self.link_path:
            try:
                if os.path.islink(self.link_path) or os.path.exists(self.link_path):
                    os.unlink(self.link_path)
                os.symlink(self.pty_slave_path, self.link_path)
                self._link_created = True
            except OSError as exc:
                logger.warning("Failed to create mirror symlink %s: %s", self.link_path, exc)

    def stop(self) -> None:
        super().stop()
        # Clean up PTY and symlink.
        try:
            os.close(self._master_fd)
        except OSError:
            pass
        try:
            os.close(self._slave_fd)
        except OSError:
            pass
        if self._link_created and self.link_path:
            try:
                os.unlink(self.link_path)
                self._link_created = False
            except OSError:
                pass
        if self._mirror_index is not None:
            _release_mirror_index(self._mirror_index)
            self._mirror_index = None

    def _run(self) -> None:
        ser_fd = self.ser.fileno()
        read_fds = [ser_fd, self._master_fd] if self.mode == "rw" else [ser_fd]

        while not self._stop.is_set():
            if self.mode == "rw":
                self._check_pause_expired()

            try:
                readable, _, _ = select.select(read_fds, [], [], 0.05)
            except (OSError, ValueError):
                if self._stop.is_set():
                    break
                time.sleep(0.1)
                continue

            for fd in readable:
                if fd == ser_fd:
                    try:
                        waiting = self.ser.in_waiting
                        data = self.ser.read(waiting or 1)
                        if data:
                            self._on_data(data)
                    except Exception:
                        if self._stop.is_set():
                            return
                        time.sleep(0.1)

                elif fd == self._master_fd:
                    try:
                        pty_data = os.read(self._master_fd, 4096)
                        if pty_data:
                            self._forward_or_drop(pty_data)
                    except OSError:
                        pass  # PTY client disconnected.

    def _on_data(self, data: bytes) -> None:
        """Write to both the buffer and the PTY master."""
        self.buffer.write(data)
        try:
            os.write(self._master_fd, data)
        except (OSError, BlockingIOError):
            pass  # PTY buffer full or client not connected — drop mirror data.

    def mirror_info(self) -> dict[str, Any] | None:
        return {
            "transport": "pty",
            "pty_path": self.pty_slave_path,
            "link": self.link_path,
            "mode": self.mode,
            "forwarding_paused": self.is_forwarding_paused,
            "dropped_while_paused": self.dropped_while_paused,
        }


# ---------------------------------------------------------------------------
# TcpMirrorSession — TCP socket tee on top of ReaderThread (cross-platform)
# ---------------------------------------------------------------------------


class TcpMirrorSession(ReaderThread):
    """Background reader that also tees serial data to a TCP client.

    Cross-platform: unlike a PTY, a socket works the same way on Windows,
    macOS, and Linux. Deliberately does NOT select() on the serial port's
    own fd (pyserial's Windows backend doesn't support that) -- instead it
    polls the serial side exactly like the base ReaderThread does, and
    services the TCP side with a short, separate, non-blocking select()
    each loop iteration (sockets ARE select()-able everywhere).

    A new client connection replaces any existing one rather than being
    refused. This is deliberate: it matches how a poll-and-reconnect script
    (e.g. telnet-watch.sh) already behaves on the client side -- drop and
    reattach freely, the mirror just takes the newest connection, with no
    stale-attachment problem for the client to detect or recover from.

    In rw mode, data received from the connected client is forwarded to the
    real serial port via the inherited, pause-gated _forward_or_drop --
    identical mechanism to the PTY transport's rw mode.
    """

    def __init__(
        self,
        ser: Any,
        buffer: SerialBuffer,
        mode: str,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        super().__init__(ser, buffer)
        self.mode = mode  # "ro" or "rw"
        self.client_connected = False
        self._client_sock: socket.socket | None = None

        self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen_sock.bind((host, port))
        self._listen_sock.listen(1)
        self._listen_sock.setblocking(False)
        bound_host, bound_port = self._listen_sock.getsockname()[:2]
        self.tcp_host: str = bound_host
        self.tcp_port: int = bound_port

    def stop(self) -> None:
        super().stop()
        if self._client_sock is not None:
            try:
                self._client_sock.close()
            except OSError:
                pass
            self._client_sock = None
            self.client_connected = False
        try:
            self._listen_sock.close()
        except OSError:
            pass

    def _run(self) -> None:
        errors = 0
        while not self._stop.is_set():
            if self.mode == "rw":
                self._check_pause_expired()
            self._service_sockets()

            try:
                waiting = self.ser.in_waiting
                data = self.ser.read(waiting) if waiting else self.ser.read(1)
                if data:
                    self._on_data(data)
                errors = 0
            except Exception:
                if self._stop.is_set():
                    break
                errors += 1
                if errors >= self._MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        "TCP mirror reader thread for %s stopping after %d consecutive errors.",
                        self.ser.port,
                        errors,
                    )
                    break
                time.sleep(0.1)

    def _service_sockets(self) -> None:
        """Accept a new client and/or read pending client->serial bytes. Never blocks."""
        read_fds = (
            [self._listen_sock] if self._client_sock is None else [self._listen_sock, self._client_sock]
        )
        try:
            readable, _, _ = select.select(read_fds, [], [], 0)
        except (OSError, ValueError):
            return

        for sock in readable:
            if sock is self._listen_sock:
                self._accept_client()
            elif sock is self._client_sock:
                self._service_client_read()

    def _accept_client(self) -> None:
        try:
            new_sock, addr = self._listen_sock.accept()
        except OSError:
            return
        if self._client_sock is not None:
            logger.info("New mirror client %s replacing previous client on %s.", addr, self.ser.port)
            try:
                self._client_sock.close()
            except OSError:
                pass
        new_sock.setblocking(False)
        self._client_sock = new_sock
        self.client_connected = True

    def _service_client_read(self) -> None:
        try:
            data = self._client_sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            data = b""  # Treat any other socket error as a disconnect.

        if not data:
            self._drop_client()
            return

        if self.mode == "rw":
            self._forward_or_drop(data)
        # ro mode: bytes from a read-only observer are simply discarded.

    def _drop_client(self) -> None:
        if self._client_sock is not None:
            try:
                self._client_sock.close()
            except OSError:
                pass
        self._client_sock = None
        self.client_connected = False

    def _on_data(self, data: bytes) -> None:
        """Write to both the buffer and the connected client, if any."""
        self.buffer.write(data)
        if self._client_sock is None:
            return
        try:
            self._client_sock.sendall(data)
        except (OSError, BlockingIOError):
            # Client gone or backed up -- drop mirror tee data, same
            # best-effort posture as the PTY transport's full-buffer case.
            self._drop_client()

    def mirror_info(self) -> dict[str, Any] | None:
        return {
            "transport": "tcp",
            "tcp_host": self.tcp_host,
            "tcp_port": self.tcp_port,
            "client_connected": self.client_connected,
            "mode": self.mode,
            "forwarding_paused": self.is_forwarding_paused,
            "dropped_while_paused": self.dropped_while_paused,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_mirror_indices_lock = threading.Lock()
_mirror_indices_in_use: set[int] = set()


def _acquire_mirror_index() -> int:
    """Return the lowest available mirror index."""
    with _mirror_indices_lock:
        idx = 0
        while idx in _mirror_indices_in_use:
            idx += 1
        _mirror_indices_in_use.add(idx)
        return idx


def _release_mirror_index(idx: int) -> None:
    """Return a mirror index to the pool."""
    with _mirror_indices_lock:
        _mirror_indices_in_use.discard(idx)


def create_reader(
    ser: Any,
    buffer: SerialBuffer,
    mirror_mode: str,
    mirror_link_base: str | None,
    mirror_transport: str = "pty",
    tcp_host: str = "127.0.0.1",
    tcp_port: int = 0,
) -> ReaderThread:
    """Create the appropriate reader for a serial connection.

    *mirror_mode*: ``"off"``, ``"ro"``, or ``"rw"``.
    *mirror_transport*: ``"pty"`` (default, Unix-only) or ``"tcp"``
    (cross-platform; *tcp_host*/*tcp_port* only apply to this transport).
    """
    if mirror_mode == "off":
        return ReaderThread(ser, buffer)

    if mirror_transport == "tcp":
        return TcpMirrorSession(ser, buffer, mode=mirror_mode, host=tcp_host, port=tcp_port)

    if not _IS_UNIX:
        return ReaderThread(ser, buffer)

    link_path: str | None = None
    mirror_index: int | None = None
    if mirror_link_base:
        mirror_index = _acquire_mirror_index()
        link_path = f"{mirror_link_base}{mirror_index}"

    session = MirrorSession(ser, buffer, mode=mirror_mode, link_path=link_path)
    session._mirror_index = mirror_index
    return session
