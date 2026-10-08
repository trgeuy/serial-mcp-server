# Changelog

## 0.2.5

### Changed
- The pacing tools (`paced.*`) are now ON by default. Before, they needed `SERIAL_MCP_PACED=1`. This fork is for vintage machines, and its `serial-mcp` skill depends on these tools; without the setting, the agent did not have them. Registered tools do nothing until the agent uses them. Set `SERIAL_MCP_PACED=0` to turn them off. A registration that already sets `SERIAL_MCP_PACED=1` keeps working.
- README: the registration no longer sets `SERIAL_MCP_PACED=1`.
- `serial-mcp` skill: the `SSSTAT` example now says what it shows (five `STAT` commands sent in one burst: the first ran, and a leftover `SS` arrived glued onto a later one), and tells the agent to explain it when it passes the example on. Before, the agent quoted `SSSTAT` to users with no explanation.

## 0.2.4

### Added
- `serial-watch` command, installed with the package next to `serial_mcp`. It watches the TCP mirror in a terminal window while the agent drives the device: it waits for the mirror, shows the device's bytes as they arrive, and connects again when the mirror drops. It runs on macOS, Linux and Windows (on Windows it also turns on the console's escape-sequence handling). Usage: `serial-watch` (localhost:2424), `serial-watch PORT`, `serial-watch HOST PORT`. It prints the same messages as the old scripts. Tested on macOS; Windows and Linux are not tested yet.

### Changed
- Each release also has `serial-mcp-server.tar.gz`: the source package under a name that does not change. With GitHub's `releases/latest/download/` link, `uv tool install "serial-mcp-server @ <that link>"` always installs the newest release, and the skill's `curl` link does the same. The install commands in the README no longer name a version.
- README Quickstart: install with `uv tool install`, then register `-- serial_mcp` at user scope with the mirror (`ro`, TCP) and paced writes on. Before, the registration ran `uvx --from <wheel URL> serial_mcp`, which put the whole URL on every `claude mcp list` line.
- The `serial-mcp` skill tells the agent to suggest `serial-watch` for the TCP mirror, in place of `nc`.

### Removed
- `examples/mirror-watch/` (`mirror-watch.sh`, `mirror-watch.ps1`): replaced by `serial-watch`. The name changed so it is not confused with altairsim's own `tools/mirror-watch.sh`, which watches altairsim's machine mirror (port 2323) and is separate and unchanged. `serial-watch` takes only a port or a host and port; it has no `altairsim` or `serial` name argument.

## 0.2.3

### Fixed
- `exclusive` (the default) now keeps every other program off the port on macOS and Linux. Before, it was only an advisory `flock()` lock: `screen` or `minicom` opened on the port by mistake got the port too. On the real Altair 8800c, `DIR` then gave the server 1 byte and `screen` the other 551, with no error. When `screen` quit, the server's connection broke (`Input/output error`). Now the server sets `TIOCEXCL` after it opens the port, and the kernel refuses every other open with "Resource busy" until the server closes the port. If a device refuses `TIOCEXCL`, the server logs a warning and keeps the advisory lock. A pseudo-terminal on macOS ignores `TIOCEXCL`, so the lock does not cover a pty.

## 0.2.2

Release packaging: the skill comes with each release. No change to the server code or the skill.

### Added
- `serial-mcp-skill.zip` on each GitHub release, next to the wheel. The zip unpacks to `serial-mcp/`. `unzip -o serial-mcp-skill.zip -d ~/.claude/skills/` installs the skill for all projects. The README Quickstart now has this step. Before, you had to copy `.claude/skills/serial-mcp/` from the source archive.

## 0.2.1

Documentation release: the `serial-mcp` skill and its pacing data. No change to the server code.

### Changed
- `serial-mcp` skill, rewritten for any vintage machine, not only the two that were measured. New: a bring-up procedure for a machine or program with no measured values (line settings, line ending, echo, slow start, measure down); a "read the failure" table that maps each kind of damage to its cause and the gap to change; a rule that each program needs its own pacing, a rule to leave 20% headroom above the lowest passing gap, and a rule to keep your own list of measured gaps per machine and program. New warnings: do not set `newline` on `serial.open` (a typed `\r` is sent as text); `eol_gap_ms` comes only after the connection's newline; check `sent_text` in a `paced.calibrate` result, because a text newline gives a false "clean" result. The Altair and UCSD Pascal values are now marked as tested examples.
- Pacing profiles: measured gaps now go in ONE user-level file for all projects, `~/.config/serial-mcp/pacing-profiles.md` (Windows: `%APPDATA%\serial-mcp\pacing-profiles.md`), outside the skill folder so a skill update cannot replace it. The skill defines a fixed table format (one section per machine: line end, gaps, wait, lowest pass / first fail, method, date) and tells the agent to read the file first, add a row after each measurement, and never fill a cell with a guess.
- `references/device-profiles.md` is now `references/pacing-examples.md`, in the new format. Added for the Altair 8800c: MBASIC 5.21 program entry (the line gap grows with line length) and CP/M `PIP <file>=CON:` (no ready sign: a start wait before the first byte; no chunks needed for a 6 KB file). The "Wait ms" column covers a wait before the first byte as well as after a prompt. CCP char gap is now 5 ms (2 ms was the edge).

## 0.2.0

First release of this fork (trgeuy/serial-mcp-server). Install it from the GitHub release, not from PyPI: the PyPI name `serial-mcp-server` is the upstream package, without these changes.

### Added
- Exclusive-forwarding pause/resume for `rw`-mode mirrors: `MirrorSession`/`TcpMirrorSession` can pause external-tool-to-serial forwarding for the duration of a multi-call agent command sequence, always auto-expiring even if never explicitly resumed. Dropped bytes are counted (`dropped_while_paused`), not buffered and replayed.
- TCP mirror transport (`SERIAL_MCP_MIRROR_TRANSPORT=tcp`, alongside the existing `pty` default): a plain socket, works on every platform including Windows (the PTY transport needs `os.openpty()`, which Windows has no equivalent for). One client at a time: a second client gets a one-line busy notice and is closed, and the first keeps the mirror. A disconnected client frees its place at once, so a simple poll-and-reconnect script always gets a clean mirror. Configurable via `SERIAL_MCP_MIRROR_TCP_HOST`/`SERIAL_MCP_MIRROR_TCP_PORT` (default: loopback, fixed port `2424` — set to `0` for an OS-assigned ephemeral port, required if mirroring more than one connection at once).
- `paced.*` tools, built in and opt-in via `SERIAL_MCP_PACED=1`: `paced.configure`, `paced.write`, `paced.calibrate`, `paced.sweep` (byte-paced writes and empirical gap tuning for UARTs that drop characters at full speed), plus `paced.exclusive_begin`/`paced.exclusive_end` (the pause/resume tools above, exposed at the tool level).
- `examples/mirror-watch/`: watch-only scripts for the TCP mirror transport -- `mirror-watch.sh` (macOS/Linux, bash only) and `mirror-watch.ps1` (Windows, PowerShell only). They need no `telnet` or `nc`, wait for the mirror, and connect again on their own after a drop. They replace the earlier `examples/telnet-watch/` wrapper, which needed a `telnet` binary (not on a clean macOS, not installed on Windows).
- `.claude/skills/serial-mcp/`: a Claude Code skill for driving real hardware with these tools -- control bytes as hex, per-connection pacing, one command at a time on an old console, the delay after a disk write on a BIOS that buffers writes, mirror modes, and gap calibration. `references/device-profiles.md` holds measured values for an Altair 8800c (CP/M 2.2) and a UCSD Pascal III system.
- `SERIAL_MCP_MIRROR_TCP_TELNET=1` (opt-in, default off): fixes double-echo in a real telnet client attached to the TCP mirror. Sends `IAC WILL ECHO`/`IAC WILL SUPPRESS-GO-AHEAD` on each new client connection, strips telnet command bytes (negotiation replies, subnegotiation blocks) out of the client's incoming stream before it can reach the serial port, and escapes a literal `0xFF` in outgoing device data as `IAC IAC` so a real telnet client's parser doesn't misread it. Off by default since a plain socket client (`nc`, test scripts) doesn't speak or need the telnet protocol.

### Fixed
- `serial.open` now locks the port by default (`exclusive` defaults to `true`). Before, two server processes (for example two agent sessions) could open the same device on macOS/Linux, and each got only part of the incoming bytes, with no error. Pass `exclusive: false` to open without the lock.
- A stopped background reader is now reported. After 10 read errors in a row (for example, an unplugged USB serial adapter) the reader stops; reads used to return empty forever while `serial.connection_status` still said the port was open. Now the status shows `reader_alive`, `reader_failed` and `reader_last_error`, and an empty read returns the error `reader_stopped`. The PTY mirror's reader now has the same 10-error limit (it used to retry forever).
- `serial.close` no longer blocks the server while the reader thread stops (up to 3 s). Other tool calls keep running.
- `serial.open` no longer leaves the serial port open when the mirror cannot start (for example, the TCP mirror port is in use by another connection or program). It closes the port and returns a `mirror_unavailable` error that names the cause.
- `rw` mirror: a byte from the mirror client during a long `paced.write` no longer stops the reader thread. The reader waited for the write lock and stopped reading the port, so the mirror and the buffer froze until the write ended. Client bytes now wait in a small queue (4 KiB) and go to the port when the write ends. Bytes still waiting when an exclusive pause starts are dropped and counted, so they cannot land inside the paused sequence.
- TCP mirror: a second client is now refused instead of replacing the first. With replacement, two auto-reconnecting watchers knocked each other off every second.
- TCP mirror on Windows: the listen socket uses `SO_EXCLUSIVEADDRUSE` instead of `SO_REUSEADDR`. On Windows, `SO_REUSEADDR` lets a second server bind a port that is already in use.
- Nested `paced.exclusive_begin`: an inner pause with a shorter timeout no longer ends the outer pause early. A nested begin can extend the pause, never shorten it.

### Changed
- `mirror_info()` now reports `transport` (`"pty"` or `"tcp"`) on every mirrored connection, plus `forwarding_paused`/`dropped_while_paused`. TCP mirrors also report `telnet` (bool).

## 0.1.3

### Fixed
- Raise minimum `mcp` SDK dependency to >=1.23.0 to exclude versions with known CVEs (CVE-2025-53366, CVE-2025-53365, CVE-2025-66416). These affect HTTP/SSE transport only — stdio servers were never vulnerable — but the wider range allowed scanners to flag the package.

## 0.1.2

### Added
- VS Code / Copilot setup instructions in README (`.vscode/mcp.json`)
- Cursor setup instructions in README (`.cursor/mcp.json`)
- `SERIAL_MCP_TOOL_SEPARATOR` env var — configurable separator for tool names (default `.`). Set to `_` for MCP clients that reject dots in tool names (e.g. Cursor).

## 0.1.1

### Fixed
- Accept string-typed numeric parameters in tool schemas (`"9600"` instead of `9600`). Some MCP clients serialize all tool arguments as strings, which caused JSON Schema validation errors on `integer` and `number` fields. Affected fields: `baudrate`, `bytesize`, `stopbits`, `timeout_ms`, `write_timeout_ms`, `nbytes`, `max_bytes`, `duration_ms`, `k`, `n`.

## 0.1.0

Initial release.

### Serial Core
- List available serial ports with device metadata (VID, PID, manufacturer, serial number)
- Open connections with configurable baud rate, byte size, parity, stop bits, timeout, and encoding
- Close connections, query connection status
- Read data with configurable byte count and timeout override
- Write data in text, hex, or base64 format, with optional newline append
- Line-oriented I/O: `serial.readline` and `serial.read_until` with custom delimiters
- Flush input/output buffers (or both)
- Control lines: set and pulse DTR/RTS (useful for hardware reset and boot mode entry)
- Duplicate port detection (rejects opening the same port twice)
- Graceful shutdown (closes all serial ports on exit)

### PTY Mirror
- Virtual clone ports via pseudo-terminals (`SERIAL_MCP_MIRROR=ro` or `rw`)
- External tools (screen, picocom, etc.) can attach to the same serial session
- Default symlink at `/tmp/serial-mcp0`, configurable via `SERIAL_MCP_MIRROR_LINK`
- macOS and Linux only

### Introspection
- `serial.connections.list` for recovering connection IDs and inspecting state

### Protocol Specs
- Markdown specs with YAML front-matter (`kind: serial-protocol`, `name`)
- Template generation, registration, indexing
- Attach specs to connections for agent reference
- Full-text search over spec content

### Tracing
- JSONL tracing of every tool call (in-memory ring buffer + file sink)
- Configurable payload logging with truncation
- `serial.trace.status` and `serial.trace.tail` for inspection

### Plugins
- User plugins in `.serial_mcp/plugins/` (single files or packages)
- Plugin contract: `TOOLS`, `HANDLERS`, optional `META` for device matching
- `SERIAL_MCP_PLUGINS` env var: `all` or comma-separated allowlist
- `serial.plugin.template` for generating plugin skeletons
- `serial.plugin.list` with metadata, `serial.plugin.load`, `serial.plugin.reload`
- Hot-reload without server restart

### Security
- Plugin path containment: `serial.plugin.load` rejects paths outside `.serial_mcp/plugins/`
- Spec path containment: `serial.spec.register` rejects paths outside the project directory
- Trace file always writes to `.serial_mcp/traces/trace.jsonl` (no configurable path)
- Symlink check on trace file path
- Input validation for hex/base64 write payloads
