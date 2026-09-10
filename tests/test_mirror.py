"""Tests for serial_mcp_server.mirror — SerialBuffer, ReaderThread, MirrorSession."""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from serial_mcp_server.mirror import (
    ReaderThread,
    SerialBuffer,
    TcpMirrorSession,
    create_reader,
)

# MirrorSession is Unix-only
_IS_UNIX = sys.platform != "win32"
if _IS_UNIX:
    from serial_mcp_server.mirror import MirrorSession


# ---------------------------------------------------------------------------
# SerialBuffer
# ---------------------------------------------------------------------------


class TestSerialBuffer:
    def test_write_and_read(self):
        buf = SerialBuffer()
        buf.write(b"hello")
        result = buf.read(10, timeout=1.0)
        assert result == b"hello"

    def test_read_returns_up_to_nbytes(self):
        buf = SerialBuffer()
        buf.write(b"hello world")
        result = buf.read(5, timeout=1.0)
        assert result == b"hello"
        # Remainder stays in buffer
        result2 = buf.read(100, timeout=0.01)
        assert result2 == b" world"

    def test_read_timeout_empty(self):
        buf = SerialBuffer()
        start = time.monotonic()
        result = buf.read(10, timeout=0.05)
        elapsed = time.monotonic() - start
        assert result == b""
        assert elapsed >= 0.04

    def test_read_blocks_until_data(self):
        buf = SerialBuffer()

        def delayed_write():
            time.sleep(0.05)
            buf.write(b"data")

        t = threading.Thread(target=delayed_write)
        t.start()
        result = buf.read(10, timeout=1.0)
        t.join()
        assert result == b"data"

    def test_read_until_delimiter(self):
        buf = SerialBuffer()
        buf.write(b"line1\r\nline2\r\n")
        result = buf.read_until(b"\r\n", max_bytes=100, timeout=1.0)
        assert result == b"line1\r\n"

    def test_read_until_max_bytes(self):
        buf = SerialBuffer()
        buf.write(b"a very long line without newline")
        result = buf.read_until(b"\n", max_bytes=10, timeout=0.05)
        assert result == b"a very lon"
        assert len(result) == 10

    def test_read_until_timeout(self):
        buf = SerialBuffer()
        buf.write(b"no newline here")
        result = buf.read_until(b"\n", max_bytes=1000, timeout=0.05)
        assert result == b"no newline here"

    def test_read_until_blocks_until_delimiter(self):
        buf = SerialBuffer()

        def delayed_write():
            time.sleep(0.05)
            buf.write(b"hello\n")

        t = threading.Thread(target=delayed_write)
        t.start()
        result = buf.read_until(b"\n", max_bytes=100, timeout=1.0)
        t.join()
        assert result == b"hello\n"

    def test_clear(self):
        buf = SerialBuffer()
        buf.write(b"data")
        assert buf.available == 4
        buf.clear()
        assert buf.available == 0

    def test_available(self):
        buf = SerialBuffer()
        assert buf.available == 0
        buf.write(b"abc")
        assert buf.available == 3

    def test_max_size_trims_oldest(self):
        buf = SerialBuffer(max_size=10)
        buf.write(b"0123456789")
        assert buf.available == 10
        buf.write(b"AB")
        assert buf.available == 10
        result = buf.read(10, timeout=0.01)
        assert result == b"23456789AB"

    def test_write_empty_noop(self):
        buf = SerialBuffer()
        buf.write(b"")
        assert buf.available == 0

    def test_concurrent_write_read(self):
        """Multiple writers + one reader, no crashes."""
        buf = SerialBuffer()
        total_written = 0
        lock = threading.Lock()

        def writer(chunk: bytes, count: int):
            nonlocal total_written
            for _ in range(count):
                buf.write(chunk)
                with lock:
                    total_written += len(chunk)
                time.sleep(0.001)

        threads = [
            threading.Thread(target=writer, args=(b"A" * 10, 50)),
            threading.Thread(target=writer, args=(b"B" * 10, 50)),
        ]
        for t in threads:
            t.start()

        read_total = 0
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            data = buf.read(100, timeout=0.01)
            read_total += len(data)
            if read_total >= 1000:
                break

        for t in threads:
            t.join()

        # Drain remaining
        remaining = buf.read(10000, timeout=0.01)
        read_total += len(remaining)
        assert read_total == total_written


# ---------------------------------------------------------------------------
# ReaderThread
# ---------------------------------------------------------------------------


class TestReaderThread:
    def test_data_flows_to_buffer(self):
        buf = SerialBuffer()
        ser = MagicMock()
        type(ser).in_waiting = PropertyMock(side_effect=[5, 0, 0, 0])
        ser.read.side_effect = [b"hello", b"", b"", b""]

        reader = ReaderThread(ser, buf)
        reader.start()
        time.sleep(0.1)
        reader.stop()

        assert buf.available >= 5
        assert buf.read(5, timeout=0.01) == b"hello"

    def test_start_stop(self):
        buf = SerialBuffer()
        ser = MagicMock()
        type(ser).in_waiting = PropertyMock(return_value=0)
        ser.read.return_value = b""

        reader = ReaderThread(ser, buf)
        reader.start()
        assert reader.alive
        reader.stop()
        assert not reader.alive

    def test_mirror_info_returns_none(self):
        buf = SerialBuffer()
        ser = MagicMock()
        reader = ReaderThread(ser, buf)
        assert reader.mirror_info() is None

    def test_has_write_lock(self):
        buf = SerialBuffer()
        ser = MagicMock()
        reader = ReaderThread(ser, buf)
        assert hasattr(reader, "write_lock")
        assert isinstance(reader.write_lock, type(threading.Lock()))

    def test_pause_resume_tracked_but_no_forwarding_to_affect(self):
        """Base ReaderThread tracks pause state faithfully -- it just never calls
        _forward_or_drop itself, so pausing here has no observable effect on
        anything (there's no external mirror client to gate in the first place)."""
        buf = SerialBuffer()
        ser = MagicMock()
        reader = ReaderThread(ser, buf)
        assert reader.is_forwarding_paused is False
        assert reader.pause_depth == 0
        applied = reader.pause_forwarding(timeout_ms=1000)
        assert applied == 1000.0
        assert reader.is_forwarding_paused is True
        assert reader.pause_depth == 1
        reader.resume_forwarding()
        assert reader.is_forwarding_paused is False
        assert reader.pause_depth == 0
        reader.resume_forwarding()  # already at zero -- must not raise or go negative
        assert reader.pause_depth == 0


# ---------------------------------------------------------------------------
# MirrorSession (Unix only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _IS_UNIX, reason="PTY mirror requires Unix")
class TestMirrorSession:
    def test_creates_pty(self):
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        mirror = MirrorSession(ser, buf, mode="ro")
        try:
            assert mirror.pty_slave_path
            assert os.path.exists(mirror.pty_slave_path)
            assert mirror.mode == "ro"
        finally:
            mirror.stop()

    def test_mirror_info(self):
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        mirror = MirrorSession(ser, buf, mode="rw")
        try:
            info = mirror.mirror_info()
            assert info is not None
            assert "pty_path" in info
            assert info["mode"] == "rw"
            assert info["link"] is None
        finally:
            mirror.stop()

    def test_symlink_creation(self, tmp_path):
        link = str(tmp_path / "testlink")
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        mirror = MirrorSession(ser, buf, mode="ro", link_path=link)
        try:
            assert os.path.islink(link)
            assert os.readlink(link) == mirror.pty_slave_path
        finally:
            mirror.stop()
        # Symlink cleaned up on stop
        assert not os.path.exists(link)

    def test_data_to_buffer_and_pty(self):
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        mirror = MirrorSession(ser, buf, mode="ro")
        try:
            # Simulate data arriving via _on_data
            mirror._on_data(b"test data")
            assert buf.read(100, timeout=0.01) == b"test data"
        finally:
            mirror.stop()

    def test_stop_cleans_up(self):
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        mirror = MirrorSession(ser, buf, mode="ro")
        mirror.stop()
        # PTY fds are closed, no error expected
        assert not mirror.alive


@pytest.mark.skipif(not _IS_UNIX, reason="PTY mirror requires Unix")
class TestExclusiveForwarding:
    """paced.exclusive_begin/end's underlying mechanism: pause/resume on MirrorSession."""

    def _make_rw_mirror(self) -> MirrorSession:
        """MirrorSession with a mock ``ser`` that has a real, never-readable fd.

        ``_run()`` calls ``select.select`` on ``ser.fileno()`` directly, which a
        bare MagicMock can't satisfy (non-integer). A pipe's read end, with the
        write end held open and never written to, is a real fd that select()
        will never report as readable -- so the ser_fd branch simply never
        fires, leaving these tests free to exercise only the PTY-forwarding
        branch under test.
        """
        ser = MagicMock()
        ser.baudrate = 115200
        pipe_r, pipe_w = os.pipe()
        ser.fileno.return_value = pipe_r
        buf = SerialBuffer()
        mirror = MirrorSession(ser, buf, mode="rw")
        mirror._test_ser_pipe = (pipe_r, pipe_w)  # closed by _stop_and_close_pipe
        return mirror

    def _stop_and_close_pipe(self, mirror: MirrorSession) -> None:
        mirror.stop()
        for fd in getattr(mirror, "_test_ser_pipe", ()):
            try:
                os.close(fd)
            except OSError:
                pass

    def test_not_paused_by_default(self):
        mirror = self._make_rw_mirror()
        try:
            assert mirror.is_forwarding_paused is False
            assert mirror.mirror_info()["forwarding_paused"] is False
            assert mirror.mirror_info()["dropped_while_paused"] == 0
        finally:
            mirror.stop()

    def test_pause_forwarding_reports_paused(self):
        mirror = self._make_rw_mirror()
        try:
            mirror.pause_forwarding(timeout_ms=1000)
            assert mirror.is_forwarding_paused is True
            assert mirror.mirror_info()["forwarding_paused"] is True
        finally:
            mirror.stop()

    def test_depth_counting_nested_pause(self):
        mirror = self._make_rw_mirror()
        try:
            assert mirror.pause_depth == 0
            mirror.pause_forwarding(timeout_ms=1000)
            assert mirror.pause_depth == 1
            mirror.pause_forwarding(timeout_ms=1000)
            assert mirror.pause_depth == 2
            mirror.resume_forwarding()
            assert mirror.pause_depth == 1
            assert mirror.is_forwarding_paused is True  # outer pause still active
            mirror.resume_forwarding()
            assert mirror.pause_depth == 0
            assert mirror.is_forwarding_paused is False
        finally:
            mirror.stop()

    def test_resume_without_pause_is_safe_noop(self):
        mirror = self._make_rw_mirror()
        try:
            mirror.resume_forwarding()  # must not raise or go negative
            assert mirror.is_forwarding_paused is False
            mirror.resume_forwarding()
            assert mirror.is_forwarding_paused is False
        finally:
            mirror.stop()

    def test_timeout_is_clamped(self):
        mirror = self._make_rw_mirror()
        try:
            assert mirror.pause_forwarding(timeout_ms=100_000) == 30_000  # clamped to max
            mirror.resume_forwarding()
            assert mirror.pause_forwarding(timeout_ms=1) == 100  # clamped to min
            mirror.resume_forwarding()
            assert mirror.pause_forwarding(timeout_ms=None) == 5_000  # default
            mirror.resume_forwarding()
        finally:
            mirror.stop()

    def test_paused_forwarding_drops_bytes_and_counts_them(self):
        mirror = self._make_rw_mirror()
        try:
            mirror.start()
            mirror.pause_forwarding(timeout_ms=5_000)
            os.write(mirror._slave_fd, b"human typed this")
            time.sleep(0.2)
            mirror.ser.write.assert_not_called()
            assert mirror.dropped_while_paused == len(b"human typed this")
        finally:
            self._stop_and_close_pipe(mirror)

    def test_resumed_forwarding_writes_to_serial(self):
        mirror = self._make_rw_mirror()
        try:
            mirror.start()
            mirror.pause_forwarding(timeout_ms=5_000)
            mirror.resume_forwarding()
            os.write(mirror._slave_fd, b"AT+VERSION\r")
            time.sleep(0.2)
            mirror.ser.write.assert_called_once_with(b"AT+VERSION\r")
        finally:
            self._stop_and_close_pipe(mirror)

    def test_pause_auto_expires_without_explicit_resume(self):
        """A caller that never resumes must not lock out the human forever."""
        mirror = self._make_rw_mirror()
        try:
            mirror.start()
            mirror.pause_forwarding(timeout_ms=100)  # minimum allowed
            assert mirror.is_forwarding_paused is True
            # Loop checks the deadline once per ~0.05s iteration; give it margin.
            time.sleep(0.35)
            assert mirror.is_forwarding_paused is False
            os.write(mirror._slave_fd, b"still here\r")
            time.sleep(0.2)
            mirror.ser.write.assert_called_once_with(b"still here\r")
        finally:
            self._stop_and_close_pipe(mirror)

    def test_ro_mode_pause_state_is_inert(self):
        """Pausing in ro mode is harmless -- nothing forwards there anyway."""
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        mirror = MirrorSession(ser, buf, mode="ro")
        try:
            mirror.pause_forwarding(timeout_ms=1000)
            assert mirror.is_forwarding_paused is True
        finally:
            mirror.stop()


# ---------------------------------------------------------------------------
# TcpMirrorSession (cross-platform -- not Unix-gated, unlike MirrorSession)
# ---------------------------------------------------------------------------


class TestTcpMirrorSession:
    def _make_mirror(self, mode: str) -> TcpMirrorSession:
        """A TcpMirrorSession whose serial side is inert -- these tests only
        exercise the socket side, so the serial-polling loop should never
        see any data (return_value, not side_effect, so it can be read any
        number of times without exhausting)."""
        ser = MagicMock()
        type(ser).in_waiting = PropertyMock(return_value=0)
        ser.read.return_value = b""
        buf = SerialBuffer()
        return TcpMirrorSession(ser, buf, mode=mode, host="127.0.0.1", port=0)

    def _connect_client(self, mirror: TcpMirrorSession) -> socket.socket:
        client = socket.create_connection((mirror.tcp_host, mirror.tcp_port), timeout=2)
        client.settimeout(2)
        return client

    def test_binds_ephemeral_port(self):
        mirror = self._make_mirror("ro")
        try:
            assert mirror.tcp_host == "127.0.0.1"
            assert mirror.tcp_port > 0
        finally:
            mirror.stop()

    def test_mirror_info_shape(self):
        mirror = self._make_mirror("rw")
        try:
            info = mirror.mirror_info()
            assert info == {
                "transport": "tcp",
                "tcp_host": "127.0.0.1",
                "tcp_port": mirror.tcp_port,
                "client_connected": False,
                "mode": "rw",
                "forwarding_paused": False,
                "dropped_while_paused": 0,
            }
        finally:
            mirror.stop()

    def test_client_receives_tee_in_ro_mode(self):
        mirror = self._make_mirror("ro")
        client = None
        try:
            mirror.start()
            client = self._connect_client(mirror)
            time.sleep(0.15)  # let the reader thread's loop accept the client
            assert mirror.client_connected is True
            mirror._on_data(b"hello from device")
            assert client.recv(100) == b"hello from device"
        finally:
            if client is not None:
                client.close()
            mirror.stop()

    def test_ro_mode_ignores_client_writes(self):
        mirror = self._make_mirror("ro")
        client = None
        try:
            mirror.start()
            client = self._connect_client(mirror)
            time.sleep(0.15)
            client.sendall(b"human typed this")
            time.sleep(0.15)
            mirror.ser.write.assert_not_called()
        finally:
            if client is not None:
                client.close()
            mirror.stop()

    def test_client_write_forwarded_in_rw_mode(self):
        mirror = self._make_mirror("rw")
        client = None
        try:
            mirror.start()
            client = self._connect_client(mirror)
            time.sleep(0.15)
            client.sendall(b"AT+VERSION\r")
            time.sleep(0.15)
            mirror.ser.write.assert_called_once_with(b"AT+VERSION\r")
        finally:
            if client is not None:
                client.close()
            mirror.stop()

    def test_paused_forwarding_drops_and_counts(self):
        mirror = self._make_mirror("rw")
        client = None
        try:
            mirror.start()
            client = self._connect_client(mirror)
            time.sleep(0.15)
            mirror.pause_forwarding(timeout_ms=5_000)
            client.sendall(b"paused bytes")
            time.sleep(0.15)
            mirror.ser.write.assert_not_called()
            assert mirror.dropped_while_paused == len(b"paused bytes")
        finally:
            if client is not None:
                client.close()
            mirror.stop()

    def test_new_client_replaces_old(self):
        mirror = self._make_mirror("ro")
        client1 = client2 = None
        try:
            mirror.start()
            client1 = self._connect_client(mirror)
            time.sleep(0.15)
            client2 = self._connect_client(mirror)
            time.sleep(0.15)

            # client1 was dropped -- its socket should now read EOF.
            assert client1.recv(100) == b""

            mirror._on_data(b"only for client2")
            assert client2.recv(100) == b"only for client2"
        finally:
            if client1 is not None:
                client1.close()
            if client2 is not None:
                client2.close()
            mirror.stop()

    def test_stop_closes_listener_and_client(self):
        mirror = self._make_mirror("ro")
        mirror.start()
        client = self._connect_client(mirror)
        time.sleep(0.15)
        mirror.stop()
        assert not mirror.alive
        client.close()


# ---------------------------------------------------------------------------
# create_reader factory
# ---------------------------------------------------------------------------


class TestCreateReader:
    def test_off_returns_reader_thread(self):
        ser = MagicMock()
        buf = SerialBuffer()
        reader = create_reader(ser, buf, "off", None)
        assert isinstance(reader, ReaderThread)
        assert not isinstance(reader, MirrorSession) if _IS_UNIX else True

    @pytest.mark.skipif(not _IS_UNIX, reason="PTY mirror requires Unix")
    def test_ro_returns_mirror_session(self):
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        reader = create_reader(ser, buf, "ro", None)
        try:
            assert isinstance(reader, MirrorSession)
            assert reader.mode == "ro"
        finally:
            reader.stop()

    @pytest.mark.skipif(not _IS_UNIX, reason="PTY mirror requires Unix")
    def test_rw_returns_mirror_session(self):
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        reader = create_reader(ser, buf, "rw", None)
        try:
            assert isinstance(reader, MirrorSession)
            assert reader.mode == "rw"
        finally:
            reader.stop()

    @pytest.mark.skipif(not _IS_UNIX, reason="PTY mirror requires Unix")
    def test_link_base_appends_index(self, tmp_path):
        ser = MagicMock()
        ser.baudrate = 115200
        buf = SerialBuffer()
        link_base = str(tmp_path / "ttyMCP")
        reader = create_reader(ser, buf, "ro", link_base)
        try:
            info = reader.mirror_info()
            assert info is not None
            assert info["link"].startswith(link_base)
        finally:
            reader.stop()

    def test_non_unix_always_returns_reader_thread(self):
        ser = MagicMock()
        buf = SerialBuffer()
        with patch("serial_mcp_server.mirror._IS_UNIX", False):
            reader = create_reader(ser, buf, "rw", None)
        assert type(reader) is ReaderThread

    def test_tcp_transport_returns_tcp_mirror_session(self):
        ser = MagicMock()
        type(ser).in_waiting = PropertyMock(return_value=0)
        ser.read.return_value = b""
        buf = SerialBuffer()
        reader = create_reader(ser, buf, "rw", None, mirror_transport="tcp")
        try:
            assert isinstance(reader, TcpMirrorSession)
            assert reader.mode == "rw"
        finally:
            reader.stop()

    def test_tcp_transport_ignores_unix_gate(self):
        """TCP works on Windows too -- unlike PTY, it must not be gated by _IS_UNIX."""
        ser = MagicMock()
        type(ser).in_waiting = PropertyMock(return_value=0)
        ser.read.return_value = b""
        buf = SerialBuffer()
        with patch("serial_mcp_server.mirror._IS_UNIX", False):
            reader = create_reader(ser, buf, "ro", None, mirror_transport="tcp")
        try:
            assert isinstance(reader, TcpMirrorSession)
        finally:
            reader.stop()

    def test_tcp_transport_honors_host_and_port(self):
        ser = MagicMock()
        type(ser).in_waiting = PropertyMock(return_value=0)
        ser.read.return_value = b""
        buf = SerialBuffer()
        reader = create_reader(ser, buf, "ro", None, mirror_transport="tcp", tcp_host="127.0.0.1", tcp_port=0)
        try:
            info = reader.mirror_info()
            assert info["tcp_host"] == "127.0.0.1"
            assert info["tcp_port"] > 0
        finally:
            reader.stop()
