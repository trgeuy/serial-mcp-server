"""Paced serial write + gap-calibration tools, and exclusive-forwarding controls.

Adds what vintage-computing terminal emulators call "pacing": a configurable
delay between characters (inter-character gap) and a separate, usually
larger, delay after a line terminator (end-of-line gap, following CR or
CR/LF). Slow or interrupt-driven UARTs on vintage hardware (e.g. an 88-SIO
on an Altair 8800) can drop characters if the host sends faster than the
device can service its receive interrupt -- pacing works around that without
needing hardware flow control.

Also adds calibration tools that send known test data at a candidate gap
setting, read back whatever the external system echoes, and diff sent vs.
received to report dropped/corrupted bytes -- so gaps can be tuned
empirically instead of guessed.

Built in, opt-in via SERIAL_MCP_PACED=1 (default off) -- same convention as
the mirror feature's SERIAL_MCP_MIRROR. Not everyone's device needs pacing,
so it's not unconditionally registered the way the core serial/introspection
tools are.

Also adds exclusive-forwarding controls for rw-mode mirrors (PTY or TCP): a
human attached to the mirror can type freely most of the time, but a
multi-call agent sequence (e.g. send a command in one tool call, its
argument in a second) can bracket itself with exclusive_begin/exclusive_end
so the human's terminal can't land bytes in the middle. Always auto-expires
(see ReaderThread.pause_forwarding in serial_mcp_server.mirror) so a crashed
or erroring sequence can't lock the human out indefinitely.

Tools:
    paced.configure       -- set/get per-connection default gaps
    paced.write           -- paced write (byte-by-byte, gaps applied)
    paced.calibrate       -- one gap setting, one send/echo/diff measurement
    paced.sweep           -- run calibrate across a set of candidate gaps
    paced.exclusive_begin -- pause rw-mirror forwarding for a multi-call sequence
    paced.exclusive_end   -- resume rw-mirror forwarding
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import string
import time
from typing import Any

from mcp.types import Tool

from serial_mcp_server.handlers_serial import MAX_READ_BYTES
from serial_mcp_server.helpers import _coerce_bool, _err, _ok
from serial_mcp_server.mirror import SerialBuffer
from serial_mcp_server.state import SerialState

# Per-connection default gaps set via paced.configure. Lost on server
# restart / connection close, same lifetime as everything else in state.
_DEFAULTS: dict[str, dict[str, float]] = {}

_MAX_SWEEP_COMBOS = 30


# ---------------------------------------------------------------------------
# Core pacing
# ---------------------------------------------------------------------------


def _split_on_terminator(payload: bytes, term: bytes) -> list[tuple[bytes, bool]]:
    """Split *payload* into (segment, ends_with_terminator) pieces.

    Each segment includes the terminator bytes when ``ends_with_terminator``
    is True. If *term* is empty, returns the whole payload as one segment
    with no terminator flag.
    """
    if not term:
        return [(payload, False)] if payload else []
    segments: list[tuple[bytes, bool]] = []
    start = 0
    while True:
        idx = payload.find(term, start)
        if idx == -1:
            if start < len(payload):
                segments.append((payload[start:], False))
            return segments
        segments.append((payload[start : idx + len(term)], True))
        start = idx + len(term)


def _write_paced_sync(
    ser: Any,
    lock: Any,
    payload: bytes,
    inter_gap_s: float,
    eol_gap_s: float,
    term_bytes: bytes,
) -> int:
    """Write *payload* one byte at a time with pacing. Runs in a worker thread.

    Delay after each byte is ``eol_gap_s`` if that byte completes the
    terminator sequence, otherwise ``inter_gap_s`` (including between the
    bytes that make up a multi-byte terminator like CR/LF -- the extra pause
    applies once, after the terminator is fully sent). No delay follows the
    very last byte written.
    """
    if lock is not None:
        lock.acquire()
    try:
        segments = _split_on_terminator(payload, term_bytes)
        n = 0
        for seg_i, (seg, has_term) in enumerate(segments):
            for i, byte_val in enumerate(seg):
                ser.write(bytes((byte_val,)))
                n += 1
                is_last_overall = seg_i == len(segments) - 1 and i == len(seg) - 1
                if is_last_overall:
                    continue
                is_last_of_segment = i == len(seg) - 1
                delay = eol_gap_s if (is_last_of_segment and has_term) else inter_gap_s
                if delay > 0:
                    time.sleep(delay)
        ser.flush()
        return n
    finally:
        if lock is not None:
            lock.release()


async def _paced_write(
    state: SerialState,
    connection_id: str,
    payload: bytes,
    inter_gap_ms: float,
    eol_gap_ms: float,
    newline: str,
) -> int:
    conn = state.get_connection(connection_id)
    term_bytes = newline.encode(conn.encoding, errors="replace")
    lock = conn.reader.write_lock if conn.reader is not None else None
    n_written = await asyncio.to_thread(
        _write_paced_sync, conn.ser, lock, payload, inter_gap_ms / 1000.0, eol_gap_ms / 1000.0, term_bytes
    )
    conn.last_seen_ts = time.time()
    return n_written


# ---------------------------------------------------------------------------
# Reading back an echo (waits for a quiet period, not just first bytes)
# ---------------------------------------------------------------------------


def _read_until_quiet_sync(
    buffer: SerialBuffer, overall_timeout_s: float, quiet_s: float, max_bytes: int
) -> bytes:
    """Accumulate bytes until *quiet_s* passes with no new data, or timeout."""
    deadline = time.monotonic() + overall_timeout_s
    out = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        room = max_bytes - len(out)
        if room <= 0:
            break
        chunk = buffer.read(room, min(quiet_s, remaining))
        if not chunk:
            if out:
                break  # had data, then silence for quiet_s -> assume echo finished
            continue  # no data yet at all -> keep waiting up to overall timeout
        out.extend(chunk)
    return bytes(out)


# ---------------------------------------------------------------------------
# Diffing sent vs. received
# ---------------------------------------------------------------------------


def _diff_report(sent: bytes, received: bytes) -> dict[str, Any]:
    matcher = difflib.SequenceMatcher(a=list(sent), b=list(received), autojunk=False)
    matched = dropped = inserted = substituted = 0
    first_mismatch: int | None = None
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
        elif tag == "delete":
            dropped += i2 - i1
            first_mismatch = i1 if first_mismatch is None else first_mismatch
        elif tag == "insert":
            inserted += j2 - j1
            first_mismatch = i1 if first_mismatch is None else first_mismatch
        elif tag == "replace":
            substituted += max(i2 - i1, j2 - j1)
            first_mismatch = i1 if first_mismatch is None else first_mismatch
    clean = dropped == 0 and inserted == 0 and substituted == 0 and len(received) > 0
    return {
        "sent_bytes": len(sent),
        "received_bytes": len(received),
        "matched_bytes": matched,
        "dropped_bytes": dropped,
        "inserted_bytes": inserted,
        "substituted_bytes": substituted,
        "first_mismatch_offset": first_mismatch,
        "clean": clean,
    }


def _default_test_lines(line_count: int, line_length: int) -> list[str]:
    charset = string.digits + string.ascii_uppercase + string.ascii_lowercase
    rep = (charset * ((line_length // len(charset)) + 1))[:line_length]
    return [f"L{i:02d}:{rep}" for i in range(max(1, line_count))]


async def _run_calibration(
    state: SerialState,
    connection_id: str,
    inter_ms: float,
    eol_ms: float,
    lines: list[str],
    newline: str,
    read_timeout_ms: int,
    quiet_ms: int,
    flush_before: bool,
) -> dict[str, Any]:
    conn = state.get_connection(connection_id)
    text = newline.join(lines) + newline
    payload = text.encode(conn.encoding, errors="replace")

    if flush_before:
        await asyncio.to_thread(conn.ser.reset_input_buffer)
        conn.buffer.clear()

    t0 = time.monotonic()
    n_written = await _paced_write(state, connection_id, payload, inter_ms, eol_ms, newline)
    write_duration_ms = round((time.monotonic() - t0) * 1000, 1)

    received = await asyncio.to_thread(
        _read_until_quiet_sync, conn.buffer, read_timeout_ms / 1000.0, quiet_ms / 1000.0, MAX_READ_BYTES
    )

    report = _diff_report(payload, received)
    return {
        "inter_char_gap_ms": inter_ms,
        "eol_gap_ms": eol_ms,
        "bytes_written": n_written,
        "write_duration_ms": write_duration_ms,
        "sent_text": text,
        "received_text": received.decode(conn.encoding, errors="replace"),
        **report,
    }


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_GAP_MS_TYPE = {"type": ["number", "string"]}

TOOLS: list[Tool] = [
    Tool(
        name="paced.configure",
        description=(
            "Set and/or get default pacing gaps for a connection, used by paced.write when "
            "inter_char_gap_ms/eol_gap_ms are omitted. Call with just connection_id to read the "
            "current defaults (0/0 if never set)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string"},
                "inter_char_gap_ms": {
                    **_GAP_MS_TYPE,
                    "description": "Default delay after each character (milliseconds).",
                },
                "eol_gap_ms": {
                    **_GAP_MS_TYPE,
                    "description": "Default extra delay after a full line terminator (CR or CR/LF) is sent.",
                },
            },
            "required": ["connection_id"],
        },
    ),
    Tool(
        name="paced.write",
        description=(
            "Write data to a serial port with pacing: a configurable inter-character gap, and a "
            "separate (usually larger) end-of-line gap applied after the line terminator is fully "
            "sent. Mirrors the pacing feature of classic terminal emulators, for UARTs that drop "
            "characters at full speed. If inter_char_gap_ms/eol_gap_ms are omitted, uses the "
            "connection's defaults from paced.configure (0 if never configured)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string"},
                "data": {"type": "string", "description": "Data to write."},
                "as": {
                    "type": "string",
                    "enum": ["text", "hex", "base64"],
                    "default": "text",
                    "description": "How to interpret 'data' (default text).",
                },
                "encoding": {
                    "type": "string",
                    "description": "Override encoding (defaults to connection encoding).",
                },
                "append_newline": {
                    "type": ["boolean", "string"],
                    "default": False,
                    "description": "Append the newline (used as the terminator for gap purposes) after data.",
                },
                "newline": {
                    "type": "string",
                    "description": (
                        "Line terminator used to detect end-of-line for eol_gap_ms, and appended when "
                        "append_newline is true. Defaults to the connection's newline (e.g. \\r\\n)."
                    ),
                },
                "inter_char_gap_ms": {
                    **_GAP_MS_TYPE,
                    "description": "Delay after each character, in milliseconds.",
                },
                "eol_gap_ms": {
                    **_GAP_MS_TYPE,
                    "description": "Extra delay after a full line terminator is sent, in milliseconds.",
                },
            },
            "required": ["connection_id", "data"],
        },
    ),
    Tool(
        name="paced.calibrate",
        description=(
            "Run one gap-tuning measurement: sends known test lines at the given inter_char_gap_ms/"
            "eol_gap_ms, waits for the external system's echo to go quiet, then diffs sent vs. "
            "received bytes and reports drops/corruption. Use this to test one candidate setting at "
            "a time, or use paced.sweep to test several automatically."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string"},
                "inter_char_gap_ms": {
                    **_GAP_MS_TYPE,
                    "default": 0,
                    "description": "Candidate inter-character gap to test.",
                },
                "eol_gap_ms": {
                    **_GAP_MS_TYPE,
                    "default": 0,
                    "description": "Candidate end-of-line gap to test.",
                },
                "test_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lines of text to send. Default: a few generated alphanumeric lines.",
                },
                "line_count": {
                    "type": ["integer", "string"],
                    "default": 3,
                    "description": "Number of generated lines if test_lines not given.",
                },
                "line_length": {
                    "type": ["integer", "string"],
                    "default": 32,
                    "description": "Length of each generated line if test_lines not given.",
                },
                "newline": {
                    "type": "string",
                    "description": "Line terminator (defaults to connection newline).",
                },
                "read_timeout_ms": {
                    "type": ["integer", "string"],
                    "default": 3000,
                    "description": "Max total time to wait for the echo (milliseconds).",
                },
                "quiet_ms": {
                    "type": ["integer", "string"],
                    "default": 300,
                    "description": "How long the input must go quiet before the echo is considered complete.",
                },
                "flush_before": {
                    "type": ["boolean", "string"],
                    "default": True,
                    "description": "Flush the input buffer before sending (recommended, avoids stale data).",
                },
            },
            "required": ["connection_id"],
        },
    ),
    Tool(
        name="paced.sweep",
        description=(
            "Run paced.calibrate across a set of candidate gaps and report which combinations echoed "
            "cleanly (no dropped/corrupted bytes). By default tests every combination of "
            "inter_char_gap_candidates_ms x eol_gap_candidates_ms (capped at 30); set pairwise=true to "
            "instead test them as matched pairs, one gap value from each list per attempt. Returns "
            "every result plus the smallest clean combination found, if any."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string"},
                "inter_char_gap_candidates_ms": {
                    "type": "array",
                    "items": {"type": ["number", "string"]},
                    "default": [0, 1, 2, 3],
                    "description": "Inter-character gap candidates to test, in milliseconds.",
                },
                "eol_gap_candidates_ms": {
                    "type": "array",
                    "items": {"type": ["number", "string"]},
                    "default": [0, 5, 10],
                    "description": "End-of-line gap candidates to test, in milliseconds.",
                },
                "pairwise": {
                    "type": ["boolean", "string"],
                    "default": False,
                    "description": "Test candidates as matched pairs instead of the full cartesian product.",
                },
                "test_lines": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lines to send each attempt.",
                },
                "line_count": {"type": ["integer", "string"], "default": 3},
                "line_length": {"type": ["integer", "string"], "default": 32},
                "newline": {
                    "type": "string",
                    "description": "Line terminator (defaults to connection newline).",
                },
                "read_timeout_ms": {"type": ["integer", "string"], "default": 3000},
                "quiet_ms": {"type": ["integer", "string"], "default": 300},
                "settle_ms": {
                    "type": ["integer", "string"],
                    "default": 200,
                    "description": "Pause between attempts, letting the device recover.",
                },
            },
            "required": ["connection_id"],
        },
    ),
    Tool(
        name="paced.exclusive_begin",
        description=(
            "Pause rw-mirror forwarding (PTY or TCP) for connection_id, so a human attached to "
            "the mirror can't land bytes in the middle of a multi-call command sequence (e.g. "
            "send a command in one call, its argument in a second). Nested begin/end pairs are "
            "depth-counted -- call exclusive_end once per exclusive_begin. Always auto-expires "
            "after timeout_ms even if exclusive_end is never called, so a crashed or erroring "
            "sequence can't lock the human out indefinitely. No-op (but still returns ok) if the "
            "connection isn't a rw-mode mirror -- there's nothing to pause."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string"},
                "timeout_ms": {
                    **_GAP_MS_TYPE,
                    "default": 5000,
                    "description": "Auto-resume after this long even without exclusive_end. Clamped to [100, 30000].",
                },
            },
            "required": ["connection_id"],
        },
    ),
    Tool(
        name="paced.exclusive_end",
        description=(
            "Resume rw-mirror forwarding (PTY or TCP) paused by exclusive_begin for "
            "connection_id. Decrements the nesting depth by one; forwarding only actually "
            "resumes once depth reaches zero. Safe to call even if not currently paused (no-op)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "connection_id": {"type": "string"},
            },
            "required": ["connection_id"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_configure(state: SerialState, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args["connection_id"]
    state.get_connection(connection_id)  # validates existence / raises KeyError
    cur = _DEFAULTS.setdefault(connection_id, {"inter_char_gap_ms": 0.0, "eol_gap_ms": 0.0})
    if "inter_char_gap_ms" in args:
        cur["inter_char_gap_ms"] = float(args["inter_char_gap_ms"])
    if "eol_gap_ms" in args:
        cur["eol_gap_ms"] = float(args["eol_gap_ms"])
    return _ok(message=f"Pacing defaults for {connection_id}.", connection_id=connection_id, **cur)


async def handle_paced_write(state: SerialState, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args["connection_id"]
    conn = state.get_connection(connection_id)
    defaults = _DEFAULTS.get(connection_id, {"inter_char_gap_ms": 0.0, "eol_gap_ms": 0.0})

    data_str = args["data"]
    fmt = args.get("as", "text")
    encoding = args.get("encoding", conn.encoding)
    append_newline = _coerce_bool(args.get("append_newline", False))
    newline = args.get("newline", conn.newline)
    inter_ms = float(args.get("inter_char_gap_ms", defaults["inter_char_gap_ms"]))
    eol_ms = float(args.get("eol_gap_ms", defaults["eol_gap_ms"]))

    if fmt == "hex":
        try:
            payload = bytes.fromhex(data_str)
        except ValueError:
            return _err("invalid_value", "data is not valid hex.")
    elif fmt == "base64":
        try:
            payload = base64.b64decode(data_str)
        except Exception:
            return _err("invalid_value", "data is not valid base64.")
    else:
        payload = data_str.encode(encoding, errors="replace")

    if append_newline:
        payload += newline.encode(encoding, errors="replace")

    n_written = await _paced_write(state, connection_id, payload, inter_ms, eol_ms, newline)

    return _ok(
        message=f"Wrote {n_written} byte(s) to {conn.port} (inter_char={inter_ms}ms, eol={eol_ms}ms).",
        bytes_written=n_written,
        inter_char_gap_ms=inter_ms,
        eol_gap_ms=eol_ms,
    )


async def handle_calibrate(state: SerialState, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args["connection_id"]
    conn = state.get_connection(connection_id)

    inter_ms = float(args.get("inter_char_gap_ms", 0))
    eol_ms = float(args.get("eol_gap_ms", 0))
    newline = args.get("newline", conn.newline)
    test_lines = args.get("test_lines") or _default_test_lines(
        int(args.get("line_count", 3)), int(args.get("line_length", 32))
    )
    read_timeout_ms = int(args.get("read_timeout_ms", 3000))
    quiet_ms = int(args.get("quiet_ms", 300))
    flush_before = _coerce_bool(args.get("flush_before", True))

    result = await _run_calibration(
        state, connection_id, inter_ms, eol_ms, test_lines, newline, read_timeout_ms, quiet_ms, flush_before
    )

    if result["received_bytes"] == 0:
        message = "No data echoed back -- check the device echoes input, wiring, and read_timeout_ms."
    elif result["clean"]:
        message = "Clean echo -- no dropped or corrupted bytes at this gap setting."
    else:
        message = (
            f"Mismatch at this gap setting: {result['dropped_bytes']} dropped, "
            f"{result['inserted_bytes']} inserted, {result['substituted_bytes']} substituted byte(s)."
        )

    return _ok(message=message, **result)


async def handle_sweep(state: SerialState, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args["connection_id"]
    conn = state.get_connection(connection_id)

    inter_candidates = [float(x) for x in args.get("inter_char_gap_candidates_ms", [0, 1, 2, 3])]
    eol_candidates = [float(x) for x in args.get("eol_gap_candidates_ms", [0, 5, 10])]
    pairwise = _coerce_bool(args.get("pairwise", False))
    newline = args.get("newline", conn.newline)
    test_lines = args.get("test_lines") or _default_test_lines(
        int(args.get("line_count", 3)), int(args.get("line_length", 32))
    )
    read_timeout_ms = int(args.get("read_timeout_ms", 3000))
    quiet_ms = int(args.get("quiet_ms", 300))
    settle_ms = int(args.get("settle_ms", 200))

    if pairwise:
        if len(inter_candidates) != len(eol_candidates):
            return _err(
                "invalid_params",
                "pairwise=true requires inter_char_gap_candidates_ms and eol_gap_candidates_ms "
                "to be the same length.",
            )
        combos = list(zip(inter_candidates, eol_candidates, strict=True))
    else:
        combos = [(i, e) for i in inter_candidates for e in eol_candidates]

    if not combos:
        return _err("invalid_params", "No candidate gap combinations given.")
    if len(combos) > _MAX_SWEEP_COMBOS:
        return _err(
            "invalid_params",
            f"{len(combos)} candidate combinations requested, max is {_MAX_SWEEP_COMBOS}. "
            "Narrow the candidate lists or use pairwise=true.",
        )

    results = []
    for idx, (inter_ms, eol_ms) in enumerate(combos):
        if idx > 0 and settle_ms > 0:
            await asyncio.sleep(settle_ms / 1000.0)
        r = await _run_calibration(
            state, connection_id, inter_ms, eol_ms, test_lines, newline, read_timeout_ms, quiet_ms, True
        )
        results.append(r)

    clean = sorted(
        (r for r in results if r["clean"]),
        key=lambda r: (r["inter_char_gap_ms"], r["eol_gap_ms"]),
    )
    recommendation = clean[0] if clean else None

    return _ok(
        message=(
            f"{len(clean)}/{len(results)} candidate(s) echoed cleanly."
            if results
            else "No candidates tested."
        ),
        results=results,
        recommendation=recommendation,
    )


async def handle_exclusive_begin(state: SerialState, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args["connection_id"]
    conn = state.get_connection(connection_id)
    if conn.reader is None:
        return _ok(message="No reader on this connection -- nothing to pause.", depth=0, applied_timeout_ms=0)

    timeout_ms = args.get("timeout_ms", 5000)
    applied_ms = conn.reader.pause_forwarding(timeout_ms=float(timeout_ms))
    depth = conn.reader.pause_depth

    # pause_forwarding() is always real (state is tracked generically on
    # every ReaderThread), so its return value alone can't tell us whether
    # pausing has any effect -- only an rw-mode mirror's loop ever calls
    # _forward_or_drop. Check the actual mirror mode instead.
    info = conn.reader.mirror_info()
    if info is None or info.get("mode") != "rw":
        message = (
            f"Depth is now {depth}, but this connection has no rw-mode mirror forwarding to "
            "pause -- no-op, nothing will be affected."
        )
    else:
        message = f"Forwarding paused for {connection_id} (depth={depth}, auto-resumes in {applied_ms:.0f}ms if not ended)."

    return _ok(message=message, depth=depth, applied_timeout_ms=applied_ms)


async def handle_exclusive_end(state: SerialState, args: dict[str, Any]) -> dict[str, Any]:
    connection_id = args["connection_id"]
    conn = state.get_connection(connection_id)
    if conn.reader is None:
        return _ok(message="No reader on this connection -- nothing to resume.", depth=0)

    conn.reader.resume_forwarding()
    depth = conn.reader.pause_depth
    message = (
        f"Forwarding still paused for {connection_id} (depth={depth})."
        if depth
        else f"Forwarding resumed for {connection_id}."
    )
    return _ok(message=message, depth=depth)


HANDLERS: dict[str, Any] = {
    "paced.configure": handle_configure,
    "paced.write": handle_paced_write,
    "paced.calibrate": handle_calibrate,
    "paced.sweep": handle_sweep,
    "paced.exclusive_begin": handle_exclusive_begin,
    "paced.exclusive_end": handle_exclusive_end,
}
