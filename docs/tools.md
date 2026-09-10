# Tools Reference

All tools return structured JSON:
`{ "ok": true, ... }` on success,
`{ "ok": false, "error": { "code": "...", "message": "..." } }` on failure.

---

## Serial Core

### serial.list_ports

List available serial ports on the system.

```json
{}
```

Returns:

```json
{
  "ok": true,
  "message": "Found 2 serial port(s).",
  "ports": [{
    "device": "/dev/ttyUSB0",
    "name": "ttyUSB0",
    "description": "USB Serial",
    "hwid": "USB VID:PID=1234:5678",
    "vid": "0x1234",
    "pid": "0x5678",
    "serial_number": "ABC123",
    "manufacturer": "FTDI",
    "product": "FT232R"
  }],
  "count": 2
}
```

Fields such as `vid`, `pid`, `serial_number`, `manufacturer`, and `product` appear when they are available.

### serial.open

Open a serial port connection. It returns a `connection_id` for use with other tools. The defaults are 115200 baud, 8N1, and a `\r\n` line terminator.

```json
{
  "port": "/dev/ttyUSB0",
  "baudrate": 115200,
  "bytesize": 8,
  "parity": "N",
  "stopbits": 1,
  "timeout_ms": 200,
  "write_timeout_ms": 200,
  "encoding": "utf-8",
  "newline": "\r\n"
}
```

Only `port` is required. All other parameters have defaults.

Returns:

```json
{
  "ok": true,
  "message": "Opened /dev/ttyUSB0 at 115200 baud.",
  "connection_id": "s1a2b3c4",
  "config": {
    "port": "/dev/ttyUSB0",
    "baudrate": 115200,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout_ms": 200,
    "write_timeout_ms": 200,
    "encoding": "utf-8",
    "newline": "'\\r\\n'"
  },
  "mirror": {
    "pty_path": "/dev/ttys004",
    "link": "/tmp/serial-mcp0",
    "mode": "ro"
  }
}
```

The `mirror` field appears only when `SERIAL_MCP_MIRROR` is `ro` or `rw`.

### serial.close

Close a serial port connection. This releases the port.

```json
{ "connection_id": "s1a2b3c4" }
```

### serial.connection_status

Check whether a serial connection is still open. Return its configuration.

```json
{ "connection_id": "s1a2b3c4" }
```

Returns `{ "ok": true, "is_open": true, "config": { ... }, "buffered_bytes": 0 }`. The response includes `mirror` when the mirror is active.

### serial.read

Read up to `nbytes` from a serial port. It returns immediately with whatever data is available within the timeout.

```json
{ "connection_id": "s1a2b3c4", "nbytes": 256, "timeout_ms": 500, "as": "text" }
```

Only `connection_id` is required. `as` can be `"text"` (default), `"hex"`, or `"base64"`.

Returns:

```json
{
  "ok": true,
  "message": "Read 12 byte(s) from /dev/ttyUSB0.",
  "n_read": 12,
  "data": "Hello world\n",
  "format": "text",
  "encoding": "utf-8"
}
```

### serial.write

Write data to a serial port.

```json
{ "connection_id": "s1a2b3c4", "data": "AT+VERSION", "append_newline": true }
```

- `as`: `"text"` (default), `"hex"`, or `"base64"`. Tells the server how to read the `data` string.
- `append_newline`: if true, adds the connection's newline (`\r\n` by default) after the data.

Returns `{ "ok": true, "message": "Wrote 12 byte(s) to /dev/ttyUSB0.", "bytes_written": 12 }`.

### serial.readline

Read a line from the serial port. It reads until it receives the newline character, or until it reaches `max_bytes`. By default, it uses the connection's newline setting.

```json
{ "connection_id": "s1a2b3c4", "timeout_ms": 1000, "max_bytes": 4096 }
```

Only `connection_id` is required. It supports `as` and `newline` overrides.

Returns `{ "ok": true, "n_read": 15, "data": "OK 200 ready\r\n", "format": "text" }`.

### serial.read_until

Read from the serial port until it receives a delimiter string, or until it reaches `max_bytes`.

```json
{ "connection_id": "s1a2b3c4", "delimiter": ">", "max_bytes": 4096 }
```

Only `connection_id` is required. Default delimiter is `\n`.

### serial.flush

Flush the serial port buffers. This discards pending data.

```json
{ "connection_id": "s1a2b3c4", "what": "both" }
```

`what` can be `"input"`, `"output"`, or `"both"` (default).

### serial.set_dtr

Set the DTR (Data Terminal Ready) control line. Usage is device-specific.

```json
{ "connection_id": "s1a2b3c4", "value": false }
```

### serial.set_rts

Set the RTS (Request To Send) control line. Usage is device-specific.

```json
{ "connection_id": "s1a2b3c4", "value": true }
```

### serial.pulse_dtr

Pulse the DTR line. It sets the line low, waits `duration_ms`, then sets it high. You can use this to reset microcontrollers.

```json
{ "connection_id": "s1a2b3c4", "duration_ms": 100 }
```

Only `connection_id` is required. Default duration is 100ms.

### serial.pulse_rts

Pulse the RTS line. It sets the line low, waits `duration_ms`, then sets it high. Some devices use RTS to enter bootloader mode.

```json
{ "connection_id": "s1a2b3c4", "duration_ms": 100 }
```

---

## Introspection

### serial.connections.list

List all open serial connections, with their status, port, configuration, and timestamps. Use this to recover connection IDs after context loss.

```json
{}
```

Returns:

```json
{
  "ok": true,
  "connections": [{
    "connection_id": "s1a2b3c4",
    "port": "/dev/ttyUSB0",
    "is_open": true,
    "baudrate": 115200,
    "encoding": "utf-8",
    "opened_at": 1700000000.0,
    "last_seen_ts": 1700000050.0,
    "buffered_bytes": 0,
    "mirror": {
      "pty_path": "/dev/ttys004",
      "link": "/tmp/serial-mcp0",
      "mode": "ro"
    }
  }],
  "count": 1
}
```

The `mirror` field appears only on connections where `SERIAL_MCP_MIRROR` is `ro` or `rw`. `buffered_bytes` shows how many unread bytes are in the connection's read buffer.

---

## Protocol Specs

These tools manage serial device protocol specs. Specs are markdown files with YAML front-matter, stored in `.serial_mcp/specs/`.

### serial.spec.template

Return a markdown template for a new serial protocol spec.

```json
{ "device_name": "MyDevice" }
```

Returns `{ "ok": true, "template": "---\nkind: serial-protocol\n...", "suggested_path": ".serial_mcp/specs/mydevice.md" }`.

### serial.spec.register

Register a spec file in the index. This validates the YAML front-matter. It requires `kind: serial-protocol` and `name` fields. The path must be inside the project directory.

```json
{ "path": ".serial_mcp/specs/mydevice.md" }
```

Returns `{ "ok": true, "spec_id": "a1b2c3d4e5f67890", "name": "MyDevice Protocol", ... }`.

### serial.spec.list

List all registered specs with their metadata.

```json
{}
```

Returns `{ "ok": true, "specs": [...], "count": 2 }`.

### serial.spec.attach

Attach a registered spec to a connection session. The server keeps this only in memory. The spec stays available through `serial.spec.get` for the life of the connection.

```json
{ "connection_id": "s1a2b3c4", "spec_id": "a1b2c3d4e5f67890" }
```

### serial.spec.get

Get the attached spec for a connection. Returns `null` if no spec is attached.

```json
{ "connection_id": "s1a2b3c4" }
```

### serial.spec.read

Read the full spec content, file path, and metadata for a given `spec_id`.

```json
{ "spec_id": "a1b2c3d4e5f67890" }
```

### serial.spec.search

Search the full text of a spec's content. Returns matching snippets with line numbers and context.

```json
{ "spec_id": "a1b2c3d4e5f67890", "query": "baud rate", "k": 10 }
```

---

## Tracing

These tools inspect the JSONL trace log. Tracing is on by default. It records every tool call.

### serial.trace.status

Return the tracing configuration and the event count.

```json
{}
```

Returns `{ "ok": true, "enabled": true, "event_count": 42, "file_path": ".serial_mcp/traces/trace.jsonl", "payloads_logged": false, "max_payload_bytes": 16384 }`.

### serial.trace.tail

Return the last N trace events. The default is 50.

```json
{ "n": 20 }
```

Returns `{ "ok": true, "events": [{ "ts": "...", "event": "tool_call_start", "tool": "serial.read", ... }, ...] }`.

---

## Plugins

These tools manage user plugins. Plugins live in `.serial_mcp/plugins/`. They add device-specific tools without changing the core server. You must set the `SERIAL_MCP_PLUGINS` environment variable to use them.

### serial.plugin.template

Return a Python plugin template. You can pre-fill it with a device name.

```json
{ "device_name": "MyDevice" }
```

Returns `{ "ok": true, "template": "\"\"\"Plugin for MyDevice...", "suggested_path": ".serial_mcp/plugins/mydevice.py" }`.

### serial.plugin.list

List loaded plugins with their tool names and metadata.

```json
{}
```

Returns:

```json
{
  "ok": true,
  "plugins": [{
    "name": "gps",
    "path": "/path/to/.serial_mcp/plugins/gps.py",
    "tools": ["gps.get_position"],
    "meta": {
      "description": "NMEA GPS module plugin",
      "device_name_contains": "GPS"
    }
  }],
  "count": 1,
  "plugins_dir": "/path/to/.serial_mcp/plugins",
  "enabled": true,
  "policy": "*"
}
```

The plugin defines the `meta` field; it is optional. Common keys are `description` and `device_name_contains`.

### serial.plugin.reload

Hot-reload a plugin by name. This re-imports the module and refreshes its tools.

```json
{ "name": "gps" }
```

Returns `{ "ok": true, "name": "gps", "tools": ["gps.get_position"], "notified": true }`.

### serial.plugin.load

Load a new plugin from a file or directory path. The path must be inside `.serial_mcp/plugins/`.

```json
{ "path": ".serial_mcp/plugins/gps.py" }
```

Returns `{ "ok": true, "name": "gps", "tools": ["gps.get_position"], "notified": true, "hint": "Plugin loaded on the server. The client may need a restart to call the new tools." }`.

---

## Paced Writes

These tools pace writes to slow or interrupt-driven UARTs. They calibrate gap sizes by testing them, and they can pause an `rw`-mode mirror's forwarding during a multi-call command sequence. These tools are built in, not a plugin. Set `SERIAL_MCP_PACED=1` to turn on all six tools below. Leave it unset, or set it to `0`, to turn them off.

### paced.configure

Set or get the default pacing gaps for a connection. `paced.write` uses these values when you omit `inter_char_gap_ms` or `eol_gap_ms`.

```json
{ "connection_id": "s1a2b3c4", "inter_char_gap_ms": 5, "eol_gap_ms": 20 }
```

Call with only `connection_id` to read the current defaults. Both default to `0` if never set. Returns `{ "ok": true, "connection_id": "...", "inter_char_gap_ms": 5.0, "eol_gap_ms": 20.0 }`.

### paced.write

Write data one byte at a time. It adds a delay after each byte (`inter_char_gap_ms`), and a separate, usually larger, delay after a full line terminator (`eol_gap_ms`). This mirrors the pacing feature of classic terminal emulators. Some UARTs drop characters when you send them faster than the UART can service its receive interrupt. These links often have no flow control to stop this.

```json
{ "connection_id": "s1a2b3c4", "data": "AT+VERSION", "append_newline": true, "inter_char_gap_ms": 5, "eol_gap_ms": 20 }
```

It takes the same `as`, `append_newline`, and `newline` options as `serial.write`. If you omit a gap value, it falls back to `paced.configure`'s defaults (`0` if never configured). Returns `{ "ok": true, "message": "...", "bytes_written": 10, "inter_char_gap_ms": 5.0, "eol_gap_ms": 20.0 }`.

### paced.calibrate

Run one gap-tuning measurement. It sends known test lines at a candidate `inter_char_gap_ms` and `eol_gap_ms`. It waits for the device's echo to go quiet, then compares what it sent against what came back.

```json
{ "connection_id": "s1a2b3c4", "inter_char_gap_ms": 2, "eol_gap_ms": 10, "line_count": 3, "line_length": 32 }
```

If you do not give `test_lines`, it generates a few alphanumeric test lines by default. It returns a comparison report: `sent_bytes`, `received_bytes`, `dropped_bytes`, `inserted_bytes`, `substituted_bytes`, `first_mismatch_offset`, and `clean`. `clean` is `true` only if nothing was dropped, inserted, or substituted, and the device sent something back.

### paced.sweep

Run `paced.calibrate` across a set of candidate gaps. Report which ones echoed cleanly.

```json
{ "connection_id": "s1a2b3c4", "inter_char_gap_candidates_ms": [0, 1, 2, 3], "eol_gap_candidates_ms": [0, 5, 10] }
```

By default, it tests the full cartesian product of the two candidate lists, capped at 30 combinations. Set `pairwise: true` to test them as matched pairs instead, one value from each list per attempt. It returns every result, plus a `recommendation`: the smallest clean combination found, or `null` if none were clean.

### paced.exclusive_begin

Pause an `rw`-mode mirror's forwarding, from the external tool to the serial port, for `connection_id`. This stops a human attached to the mirror from landing bytes in the middle of a multi-call agent command sequence. For example, the agent might send a command in one tool call and its argument in a second.

```json
{ "connection_id": "s1a2b3c4", "timeout_ms": 5000 }
```

This call is depth-counted. Nested `exclusive_begin` calls stack, and forwarding resumes only once every matching `exclusive_end` call has run. **It always expires** after `timeout_ms` (clamped to `[100, 30000]`, default `5000`), even if you never call `exclusive_end`. This means a crashed or erroring sequence can never lock a human out of the mirror. If the connection has no `rw`-mode mirror, this call does nothing and still returns `ok: true`, since there is nothing to pause. Returns `{ "ok": true, "message": "...", "depth": 1, "applied_timeout_ms": 5000.0 }`.

### paced.exclusive_end

Resume forwarding paused by `paced.exclusive_begin`.

```json
{ "connection_id": "s1a2b3c4" }
```

This decrements the nesting depth by one. Forwarding resumes only once the depth reaches zero. It is safe to call even if nothing is paused; in that case it does nothing. Returns `{ "ok": true, "message": "...", "depth": 0 }`.
