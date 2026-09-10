"""Tests for serial_mcp_server.handlers_paced -- paced writes, gap calibration,
and exclusive-forwarding controls."""

from __future__ import annotations

import sys

import pytest

from serial_mcp_server.handlers_paced import (
    _DEFAULTS,
    HANDLERS,
    TOOLS,
    _default_test_lines,
    _diff_report,
    _split_on_terminator,
    handle_calibrate,
    handle_configure,
    handle_exclusive_begin,
    handle_exclusive_end,
    handle_paced_write,
    handle_sweep,
)
from serial_mcp_server.mirror import ReaderThread

_IS_UNIX = sys.platform != "win32"
if _IS_UNIX:
    from serial_mcp_server.mirror import MirrorSession


@pytest.fixture(autouse=True)
def _clear_paced_defaults():
    """_DEFAULTS is module-level state, shared across tests -- reset each time."""
    _DEFAULTS.clear()
    yield
    _DEFAULTS.clear()


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    def test_all_tools_have_handlers(self):
        assert {t.name for t in TOOLS} == set(HANDLERS.keys())

    def test_tool_count(self):
        assert len(TOOLS) == 6


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestSplitOnTerminator:
    def test_no_terminator_present(self):
        assert _split_on_terminator(b"hello", b"\r\n") == [(b"hello", False)]

    def test_single_terminator_at_end(self):
        assert _split_on_terminator(b"hello\r\n", b"\r\n") == [(b"hello\r\n", True)]

    def test_multiple_lines(self):
        assert _split_on_terminator(b"a\r\nb\r\nc", b"\r\n") == [
            (b"a\r\n", True),
            (b"b\r\n", True),
            (b"c", False),
        ]

    def test_empty_payload(self):
        assert _split_on_terminator(b"", b"\r\n") == []

    def test_empty_terminator_returns_whole_payload_as_one_segment(self):
        assert _split_on_terminator(b"hello", b"") == [(b"hello", False)]


class TestDiffReport:
    def test_identical_is_clean(self):
        r = _diff_report(b"hello", b"hello")
        assert r["clean"] is True
        assert r["dropped_bytes"] == 0
        assert r["matched_bytes"] == 5

    def test_empty_received_is_not_clean(self):
        r = _diff_report(b"hello", b"")
        assert r["clean"] is False
        assert r["received_bytes"] == 0

    def test_dropped_byte_detected(self):
        r = _diff_report(b"hello", b"hllo")
        assert r["clean"] is False
        assert r["dropped_bytes"] == 1
        assert r["first_mismatch_offset"] == 1

    def test_substituted_byte_detected(self):
        r = _diff_report(b"hello", b"hxllo")
        assert r["clean"] is False
        assert r["substituted_bytes"] >= 1


class TestDefaultTestLines:
    def test_line_count_and_length(self):
        lines = _default_test_lines(3, 16)
        assert len(lines) == 3
        for line in lines:
            # "L%02d:" prefix (4 chars, e.g. "L00:") + line_length of payload
            assert len(line) == 4 + 16

    def test_minimum_one_line(self):
        assert len(_default_test_lines(0, 8)) == 1


# ---------------------------------------------------------------------------
# paced.configure
# ---------------------------------------------------------------------------


class TestConfigure:
    async def test_defaults_are_zero_when_unset(self, connected_entry):
        state, conn = connected_entry
        result = await handle_configure(state, {"connection_id": conn.connection_id})
        assert result["ok"]
        assert result["inter_char_gap_ms"] == 0.0
        assert result["eol_gap_ms"] == 0.0

    async def test_set_and_read_back(self, connected_entry):
        state, conn = connected_entry
        await handle_configure(
            state, {"connection_id": conn.connection_id, "inter_char_gap_ms": 5, "eol_gap_ms": 20}
        )
        result = await handle_configure(state, {"connection_id": conn.connection_id})
        assert result["inter_char_gap_ms"] == 5.0
        assert result["eol_gap_ms"] == 20.0

    async def test_partial_update_leaves_other_gap_untouched(self, connected_entry):
        state, conn = connected_entry
        await handle_configure(
            state, {"connection_id": conn.connection_id, "inter_char_gap_ms": 5, "eol_gap_ms": 20}
        )
        await handle_configure(state, {"connection_id": conn.connection_id, "inter_char_gap_ms": 9})
        result = await handle_configure(state, {"connection_id": conn.connection_id})
        assert result["inter_char_gap_ms"] == 9.0
        assert result["eol_gap_ms"] == 20.0

    async def test_unknown_connection_raises(self, serial_state):
        with pytest.raises(KeyError):
            await handle_configure(serial_state, {"connection_id": "nope"})


# ---------------------------------------------------------------------------
# paced.write
# ---------------------------------------------------------------------------


class TestPacedWrite:
    async def test_writes_each_byte_and_flushes(self, connected_entry):
        state, conn = connected_entry
        result = await handle_paced_write(state, {"connection_id": conn.connection_id, "data": "AT"})
        assert result["ok"]
        assert result["bytes_written"] == 2
        assert conn.ser.write.call_count == 2  # one call per byte
        conn.ser.flush.assert_called_once()

    async def test_append_newline_uses_connection_default(self, connected_entry):
        state, conn = connected_entry  # conn.newline == "\n" per conftest fixture
        result = await handle_paced_write(
            state, {"connection_id": conn.connection_id, "data": "AT", "append_newline": True}
        )
        assert result["bytes_written"] == 3  # A, T, \n

    async def test_hex_encoding(self, connected_entry):
        state, conn = connected_entry
        result = await handle_paced_write(
            state, {"connection_id": conn.connection_id, "data": "4449520d", "as": "hex"}
        )
        assert result["ok"]
        assert result["bytes_written"] == 4

    async def test_invalid_hex_errors(self, connected_entry):
        state, conn = connected_entry
        result = await handle_paced_write(
            state, {"connection_id": conn.connection_id, "data": "zz", "as": "hex"}
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_value"

    async def test_base64_encoding(self, connected_entry):
        state, conn = connected_entry
        result = await handle_paced_write(
            state, {"connection_id": conn.connection_id, "data": "QUI=", "as": "base64"}
        )
        assert result["ok"]
        assert result["bytes_written"] == 2  # "AB"

    async def test_invalid_base64_errors(self, connected_entry):
        state, conn = connected_entry
        result = await handle_paced_write(
            state, {"connection_id": conn.connection_id, "data": "not valid base64!!", "as": "base64"}
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_value"

    async def test_uses_configured_defaults_when_gaps_omitted(self, connected_entry):
        state, conn = connected_entry
        await handle_configure(
            state, {"connection_id": conn.connection_id, "inter_char_gap_ms": 7, "eol_gap_ms": 30}
        )
        result = await handle_paced_write(state, {"connection_id": conn.connection_id, "data": "A"})
        assert result["inter_char_gap_ms"] == 7.0
        assert result["eol_gap_ms"] == 30.0

    async def test_explicit_gaps_override_defaults(self, connected_entry):
        state, conn = connected_entry
        await handle_configure(
            state, {"connection_id": conn.connection_id, "inter_char_gap_ms": 7, "eol_gap_ms": 30}
        )
        result = await handle_paced_write(
            state, {"connection_id": conn.connection_id, "data": "A", "inter_char_gap_ms": 0, "eol_gap_ms": 0}
        )
        assert result["inter_char_gap_ms"] == 0.0
        assert result["eol_gap_ms"] == 0.0


# ---------------------------------------------------------------------------
# paced.calibrate / paced.sweep
# ---------------------------------------------------------------------------


def _make_echoing_ser(conn):
    """Patch conn.ser.write so every byte written is immediately fed back
    into conn.buffer, simulating a device with a perfect echo."""

    def _echo_write(data: bytes) -> int:
        conn.buffer.write(data)
        return len(data)

    conn.ser.write.side_effect = _echo_write


class TestCalibrate:
    async def test_clean_echo(self, connected_entry):
        state, conn = connected_entry
        _make_echoing_ser(conn)
        result = await handle_calibrate(
            state,
            {
                "connection_id": conn.connection_id,
                "line_count": 1,
                "line_length": 8,
                "read_timeout_ms": 500,
                "quiet_ms": 50,
            },
        )
        assert result["ok"]
        assert result["clean"] is True
        assert result["dropped_bytes"] == 0
        assert "Clean echo" in result["message"]

    async def test_no_echo_at_all(self, connected_entry):
        state, conn = connected_entry  # ser.write does nothing to conn.buffer -- no echo
        result = await handle_calibrate(
            state,
            {
                "connection_id": conn.connection_id,
                "line_count": 1,
                "line_length": 8,
                "read_timeout_ms": 200,
                "quiet_ms": 50,
            },
        )
        assert result["ok"]
        assert result["received_bytes"] == 0
        assert "No data echoed back" in result["message"]

    async def test_dropped_byte_reported(self, connected_entry):
        state, conn = connected_entry
        calls = {"n": 0}

        def _drop_first_byte_only(data: bytes) -> int:
            # paced.write sends one byte per ser.write() call -- drop just the
            # very first call in the whole sequence, echo every call after it.
            calls["n"] += 1
            if calls["n"] > 1:
                conn.buffer.write(data)
            return len(data)

        conn.ser.write.side_effect = _drop_first_byte_only
        result = await handle_calibrate(
            state,
            {
                "connection_id": conn.connection_id,
                "line_count": 1,
                "line_length": 8,
                "read_timeout_ms": 500,
                "quiet_ms": 50,
            },
        )
        assert result["ok"]
        assert result["clean"] is False
        assert result["dropped_bytes"] > 0
        assert "dropped" in result["message"]


class TestSweep:
    async def test_pairwise_length_mismatch_errors(self, connected_entry):
        state, conn = connected_entry
        result = await handle_sweep(
            state,
            {
                "connection_id": conn.connection_id,
                "inter_char_gap_candidates_ms": [0, 1],
                "eol_gap_candidates_ms": [0, 1, 2],
                "pairwise": True,
            },
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_params"

    async def test_too_many_combos_errors(self, connected_entry):
        state, conn = connected_entry
        result = await handle_sweep(
            state,
            {
                "connection_id": conn.connection_id,
                "inter_char_gap_candidates_ms": list(range(10)),
                "eol_gap_candidates_ms": list(range(10)),  # 100 combos > _MAX_SWEEP_COMBOS
            },
        )
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_params"

    async def test_recommends_smallest_clean_combo(self, connected_entry):
        state, conn = connected_entry
        _make_echoing_ser(conn)
        result = await handle_sweep(
            state,
            {
                "connection_id": conn.connection_id,
                "inter_char_gap_candidates_ms": [0, 5],
                "eol_gap_candidates_ms": [0],
                "line_count": 1,
                "line_length": 4,
                "read_timeout_ms": 300,
                "quiet_ms": 50,
                "settle_ms": 0,
            },
        )
        assert result["ok"]
        assert len(result["results"]) == 2
        assert result["recommendation"] is not None
        assert result["recommendation"]["inter_char_gap_ms"] == 0  # smallest clean combo


# ---------------------------------------------------------------------------
# paced.exclusive_begin / paced.exclusive_end
# ---------------------------------------------------------------------------


class TestExclusiveBeginEnd:
    async def test_no_reader_is_a_safe_noop(self, connected_entry):
        state, conn = connected_entry
        conn.reader = None
        begin = await handle_exclusive_begin(state, {"connection_id": conn.connection_id})
        assert begin["ok"]
        assert begin["depth"] == 0
        end = await handle_exclusive_end(state, {"connection_id": conn.connection_id})
        assert end["ok"]
        assert end["depth"] == 0

    async def test_plain_reader_reports_noop_message(self, connected_entry):
        """A plain ReaderThread (no mirror at all) tracks depth for real, but
        pausing has no effect -- the message must say so explicitly."""
        state, conn = connected_entry
        conn.reader = ReaderThread(conn.ser, conn.buffer)
        result = await handle_exclusive_begin(
            state, {"connection_id": conn.connection_id, "timeout_ms": 1000}
        )
        assert result["ok"]
        assert result["depth"] == 1
        assert "no-op" in result["message"]
        assert "rw-mode mirror" in result["message"]

    async def test_ro_mirror_reports_noop_message(self, connected_entry):
        """ro mode never forwards anything either, same as a plain reader."""
        state, conn = connected_entry
        reader = ReaderThread(conn.ser, conn.buffer)
        reader.mirror_info = lambda: {"mode": "ro"}
        conn.reader = reader
        result = await handle_exclusive_begin(state, {"connection_id": conn.connection_id})
        assert result["ok"]
        assert "no-op" in result["message"]

    @pytest.mark.skipif(not _IS_UNIX, reason="rw-mode mirror forwarding requires Unix (PTY)")
    async def test_rw_mirror_pauses_for_real(self, connected_entry):
        state, conn = connected_entry
        ser = conn.ser
        ser.baudrate = 115200
        mirror = MirrorSession(ser, conn.buffer, mode="rw")
        conn.reader = mirror
        try:
            result = await handle_exclusive_begin(
                state, {"connection_id": conn.connection_id, "timeout_ms": 2000}
            )
            assert result["ok"]
            assert result["depth"] == 1
            assert result["applied_timeout_ms"] == 2000.0
            assert "Forwarding paused" in result["message"]
            assert mirror.is_forwarding_paused is True

            end_result = await handle_exclusive_end(state, {"connection_id": conn.connection_id})
            assert end_result["ok"]
            assert end_result["depth"] == 0
            assert "resumed" in end_result["message"]
            assert mirror.is_forwarding_paused is False
        finally:
            mirror.stop()

    async def test_nested_depth_via_handlers(self, connected_entry):
        state, conn = connected_entry
        conn.reader = ReaderThread(conn.ser, conn.buffer)

        r1 = await handle_exclusive_begin(state, {"connection_id": conn.connection_id})
        r2 = await handle_exclusive_begin(state, {"connection_id": conn.connection_id})
        assert r1["depth"] == 1
        assert r2["depth"] == 2

        e1 = await handle_exclusive_end(state, {"connection_id": conn.connection_id})
        assert e1["depth"] == 1
        assert "still paused" in e1["message"]
        e2 = await handle_exclusive_end(state, {"connection_id": conn.connection_id})
        assert e2["depth"] == 0

    async def test_end_without_begin_is_safe_noop(self, connected_entry):
        state, conn = connected_entry
        conn.reader = ReaderThread(conn.ser, conn.buffer)
        result = await handle_exclusive_end(state, {"connection_id": conn.connection_id})
        assert result["ok"]
        assert result["depth"] == 0
        assert result["message"] == f"Forwarding resumed for {conn.connection_id}."

    async def test_timeout_is_clamped_via_handler(self, connected_entry):
        state, conn = connected_entry
        conn.reader = ReaderThread(conn.ser, conn.buffer)
        result = await handle_exclusive_begin(
            state, {"connection_id": conn.connection_id, "timeout_ms": 999999}
        )
        assert result["applied_timeout_ms"] == 30_000.0
