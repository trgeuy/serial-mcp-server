# Serial MCP Server

<!-- mcp-name: io.github.trgeuy/serial-mcp-server -->

![MCP](https://img.shields.io/badge/MCP-compatible-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Serial](https://img.shields.io/badge/Serial-RS232%2FUART-green)

This is a stateful serial port Model Context Protocol (MCP) server for developer tools and AI agents.
It works with Claude Code, VS Code with Copilot, and any MCP-compatible runtime. It communicates over **stdio**. It uses [pyserial](https://github.com/pyserial/pyserial) for serial access on macOS, Windows, and Linux.

> **Example:** Ask Claude Code to list the serial ports, connect to your microcontroller, reset it with DTR, and read the boot banner from the device.

### About this fork

This project is a fork of [es617/serial-mcp-server](https://github.com/es617/serial-mcp-server). It adds features for driving vintage and other real hardware over a live serial link:

- A cross-platform TCP mirror transport. The original mirror works only over PTY, on macOS and Linux.
- Exclusive-forwarding pause and resume. This lets an agent and a human share an `rw`-mode mirror safely.
- Built-in paced writes with gap calibration. This helps UARTs that drop characters at full speed.

See [CHANGELOG.md](CHANGELOG.md) for the full list. Everything from the original still works. This fork only adds features; it does not rewrite them.

---

## Why this exists
Have you ever copied and pasted commands into `screen` or `minicom`? Have you guessed baud rates, toggled DTR to start a bootloader, or run the same test sequence 20 times by hand? This server is for you.


You have a serial device. You want an AI agent to talk to it: to open a port, send commands, read responses, and debug protocols. This server makes that possible.

It gives any MCP-compatible agent a full set of serial tools. These include listing ports, opening connections, reading, writing, line-oriented I/O, and control line commands. It also adds protocol specs and device plugins. These let the agent reason about device behavior, not just raw bytes.

The agent calls these tools and gets structured JSON back. It reasons about what to do next. You do not need to type commands into a terminal at every step.

**What agents can do with it:**

- **Develop and debug.** You connect to your device, send commands, read responses, and diagnose issues in conversation. Examples: boot banners, prompts, error codes.
- **Iterate on new firmware.** You attach a protocol spec. The agent then understands your command set, boot modes, and output format as they change.
- **Automate test flows.** The agent resets the device with DTR, waits for the prompt, runs a command sequence, and checks the output.
- **Explore unknown devices.** The agent probes command sets, finds prompts, and infers message formats.
- **Build serial automation.** Examples: long-running test rigs, manufacturing bring-up, and CI hardware smoke tests.

---

## Who is this for?

- **Embedded engineers.** Iterate faster on serial protocols. Debug in conversation. Automate test sequences.
- **Hobbyists and makers.** Work with serial devices without writing boilerplate code. Let the agent help you reverse-engineer simple protocols.
- **QA and test engineers.** Build repeatable serial test suites with plugin tools.
- **Support and field engineers.** Diagnose serial device issues in conversation, without special tools.
- **Researchers.** Automate data collection from serial devices. Explore device capabilities systematically.

---

## Quickstart (Claude Code)

```bash
pip install git+https://github.com/trgeuy/serial-mcp-server.git
```

Register the MCP server with Claude Code:

```bash
claude mcp add serial -- serial_mcp
```

Then in Claude Code, try:

> "List available serial ports and connect to the one on /dev/ttyUSB0 at 115200 baud."

<p align="center"><img src="https://raw.githubusercontent.com/trgeuy/serial-mcp-server/main/docs/assets/scan.gif" alt="Scanning serial ports" width="600"></p>

---

## What the agent can do

Once connected, the agent has full serial capabilities:

- **List ports** to find the available serial devices.
- **Open and close** connections. Set the baud rate, parity, stop bits, and encoding.
- **Read and write** data in text, hex, or base64 format.
- **Line-oriented I/O.** Use `readline` and `read_until` for text-based protocols.
- **Control lines.** Set or pulse DTR and RTS. Use this for a hardware reset or to enter boot mode.
- **Flush** the input and output buffers.
- **Attach protocol specs** so the agent understands device-specific commands and data formats.
- **Use plugins** for high-level device actions instead of raw reads and writes.
- **Create specs and plugins** for new devices, so future sessions already know your protocol.
- **Mirroring.** Attach `screen`, `minicom`, `telnet`, or a custom script to the same serial session the agent uses. This works over a virtual device file (PTY, macOS and Linux only) or a plain TCP socket (works on Windows too).

The agent can run multi-step flows on its own. For example, it can toggle reset, wait for the prompt, send an init sequence, and stream the output.

At a high level:

**Raw Serial → Protocol Spec → Plugin**

Start with raw serial tools. Move up the stack as you understand your device protocol and it becomes repeatable.

---

## Install (development)

Editable install from repo root:

```bash
pip install -e .
```

Or with uv:

```bash
uv pip install -e .
```

> MCP is a protocol. This server works with any MCP-compatible client. Below are setup instructions for the most common clients.

## Add to Claude Code

```bash
# Standard setup
claude mcp add serial -- serial_mcp

# Or run as a module
claude mcp add serial -- python -m serial_mcp_server

# Enable all plugins
claude mcp add serial -e SERIAL_MCP_PLUGINS=all -- serial_mcp

# Enable specific plugins only
claude mcp add serial -e SERIAL_MCP_PLUGINS=mydevice,ota -- serial_mcp

# Debug logging
claude mcp add serial -e SERIAL_MCP_LOG_LEVEL=DEBUG -- serial_mcp
```

## Add to VS Code / Copilot

Add to your project's `.vscode/mcp.json` (or create it):

```json
{
  "servers": {
    "serial": {
      "type": "stdio",
      "command": "serial_mcp",
      "args": [],
      "env": {
        "SERIAL_MCP_PLUGINS": "all"
      }
    }
  }
}
```

Adjust `env` to match your needs:

- Set `SERIAL_MCP_PLUGINS` to specific plugin names.
- Add `SERIAL_MCP_MIRROR` for mirroring. On Windows, also add `SERIAL_MCP_MIRROR_TRANSPORT=tcp`.
- Add `SERIAL_MCP_PACED=1` for the pacing tools.

## Add to Cursor

Add to your project's `.cursor/mcp.json` (or create it). Cursor does not support dots in tool names. Set `SERIAL_MCP_TOOL_SEPARATOR` to `_`:

```json
{
  "mcpServers": {
    "serial": {
      "command": "serial_mcp",
      "args": [],
      "env": {
        "SERIAL_MCP_PLUGINS": "all",
        "SERIAL_MCP_TOOL_SEPARATOR": "_"
      }
    }
  }
}
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SERIAL_MCP_MAX_CONNECTIONS` | `10` | The maximum number of serial connections open at once. |
| `SERIAL_MCP_PLUGINS` | disabled | The plugin policy. Set to `all` to allow every plugin, or to a list like `name1,name2` to allow only those plugins. Leave unset to disable plugins. |
| `SERIAL_MCP_MIRROR` | `off` | The mirror mode. Use `off`, `ro` (read-only), or `rw` (read-write). |
| `SERIAL_MCP_MIRROR_TRANSPORT` | `pty` | The mirror transport. Use `pty` for a virtual device file (macOS and Linux only), or `tcp` for a plain socket (works on Windows too). Windows has no PTY equivalent. |
| `SERIAL_MCP_MIRROR_LINK` | `/tmp/serial-mcp` | PTY transport only. This is the base path for the symlinks. Connections get a number, for example `/tmp/serial-mcp0`, `/tmp/serial-mcp1`. |
| `SERIAL_MCP_MIRROR_TCP_HOST` | `127.0.0.1` | TCP transport only. This is the bind address for the mirror socket. |
| `SERIAL_MCP_MIRROR_TCP_PORT` | `2424` | TCP transport only. This is the bind port. Set it to `0` to let the OS pick a free port instead. `serial.open`'s response reports the actual port either way. Use `0` if you mirror more than one connection at once: a fixed port can bind to only one connection's mirror at a time. |
| `SERIAL_MCP_MIRROR_TCP_TELNET` | `0` | TCP transport only. Set to `1` to negotiate telnet echo handling and fix double-echo in a real telnet client. Leave off for plain socket clients (`nc`, test scripts). |
| `SERIAL_MCP_PACED` | disabled | Turns on the paced-write, gap-calibration, and exclusive-forwarding tools (`paced.*`). Set to `1` to turn them on. |
| `SERIAL_MCP_LOG_LEVEL` | `WARNING` | The Python log level (`DEBUG`, `INFO`, `WARNING`, or `ERROR`). Logs go to stderr. |
| `SERIAL_MCP_TRACE` | enabled | JSONL tracing of every tool call. Set to `0`, `false`, or `no` to disable. |
| `SERIAL_MCP_TRACE_PAYLOADS` | disabled | Adds write `data` to the traced arguments. By default, this data is removed. |
| `SERIAL_MCP_TRACE_MAX_BYTES` | `16384` | The most payload characters allowed before truncation. This only applies when `TRACE_PAYLOADS` is on. |
| `SERIAL_MCP_TOOL_SEPARATOR` | `.` | The character used to separate parts of a tool name. Set to `_` for MCP clients that reject dots in tool names, for example Cursor. |

---

## Tools

| Category | Tools |
|---|---|
| **Serial Core** | `serial.list_ports`, `serial.open`, `serial.close`, `serial.connection_status`, `serial.read`, `serial.write`, `serial.readline`, `serial.read_until`, `serial.flush`, `serial.set_dtr`, `serial.set_rts`, `serial.pulse_dtr`, `serial.pulse_rts` |
| **Introspection** | `serial.connections.list` |
| **Protocol Specs** | `serial.spec.template`, `serial.spec.register`, `serial.spec.list`, `serial.spec.attach`, `serial.spec.get`, `serial.spec.read`, `serial.spec.search` |
| **Tracing** | `serial.trace.status`, `serial.trace.tail` |
| **Plugins** | `serial.plugin.template`, `serial.plugin.list`, `serial.plugin.reload`, `serial.plugin.load` |
| **Paced Writes** (`SERIAL_MCP_PACED=1`) | `paced.configure`, `paced.write`, `paced.calibrate`, `paced.sweep`, `paced.exclusive_begin`, `paced.exclusive_end` |

---

## Protocol Specs

Specs are markdown files. They describe a serial device's protocol: connection settings, message format, commands, and multi-step flows. They live in `.serial_mcp/specs/` and teach the agent what the byte stream means.

Without a spec, the agent can still open a port and exchange data. With a spec, it knows what commands to send, what responses to expect, and what the data means.

You can create specs by telling the agent about your device. Paste a datasheet, describe the protocol, or let the agent explore the device and document what it finds. The agent then generates the spec file, registers it, and uses it in future sessions. You can also write specs by hand.

---

## Plugins

Plugins add device-specific shortcut tools to the server. Instead of the agent building raw read and write sequences, a plugin gives it a high-level action, for example `mydevice.read_temp` or `ota.upload_firmware`.

The agent can also **generate** Python plugins, with your approval. It explores a device and writes a plugin based on what it learns. Future sessions then get shortcut tools, with no manual coding needed.

To enable plugins:

```bash
# Enable all plugins
claude mcp add serial -e SERIAL_MCP_PLUGINS=all -- serial_mcp

# Enable specific plugins only
claude mcp add serial -e SERIAL_MCP_PLUGINS=mydevice,ota -- serial_mcp
```

To edit an already-loaded plugin, use `serial.plugin.reload`. No restart is needed.

---

## Tracing

Every tool call is traced to `.serial_mcp/traces/trace.jsonl` and to an in-memory ring buffer of the last 2000 events. Tracing is **on by default**. Set `SERIAL_MCP_TRACE=0` to turn it off.

### Event format

Two events per tool call:

```jsonl
{"ts":"2025-01-01T00:00:00.000Z","event":"tool_call_start","tool":"serial.read","args":{"connection_id":"s1"},"connection_id":"s1"}
{"ts":"2025-01-01T00:00:00.050Z","event":"tool_call_end","tool":"serial.read","ok":true,"error_code":null,"duration_ms":50,"connection_id":"s1"}
```

- `connection_id` comes from the arguments, when present.
- Write `data` is removed from traced arguments by default. Set `SERIAL_MCP_TRACE_PAYLOADS=1` to keep it.

### Inspecting the trace

Use `serial.trace.status` to check the configuration and event count. Use `serial.trace.tail` to get recent events. You do not need to read the file directly.

---

## Mirror

When the MCP server owns a serial port, most OSes prevent any other process from opening it. Mirroring creates a second, external-facing copy of the same byte stream. Other tools, such as `screen`, `minicom`, logic analyzers, telnet, and custom scripts, can connect to this copy at the same time.

There are two transports. Pick one with `SERIAL_MCP_MIRROR_TRANSPORT`. See [docs/concepts.md](docs/concepts.md#mirror-watch-or-share-a-connection-with-an-external-tool) for the full architecture and a transport comparison table.

### PTY transport (default, macOS/Linux only)

A virtual device file. Any tool that expects a real serial device, such as `screen` or `minicom`, can open it directly.

```bash
claude mcp add serial \
  -e SERIAL_MCP_MIRROR=ro \
  -- serial_mcp
```

After opening a connection, the response includes the mirror path:

```json
{ "mirror": { "transport": "pty", "pty_path": "/dev/ttys004", "link": "/tmp/serial-mcp0", "mode": "ro" } }
```

In another terminal, connect with the symlink path:

```bash
screen /tmp/serial-mcp0 115200
```

### TCP transport (every platform, including Windows)

A plain network socket instead of a device file. Use this on Windows, since Windows has no PTY equivalent.

```bash
claude mcp add serial \
  -e SERIAL_MCP_MIRROR=ro \
  -e SERIAL_MCP_MIRROR_TRANSPORT=tcp \
  -- serial_mcp
```

The response reports the actual bound host and port:

```json
{ "mirror": { "transport": "tcp", "tcp_host": "127.0.0.1", "tcp_port": 2424, "mode": "ro" } }
```

It defaults to a fixed port, `2424`, so client scripts can hardcode it. If you mirror more than one connection at once, a fixed port will not work — only one connection can bind it at a time. Set `SERIAL_MCP_MIRROR_TCP_PORT=0` instead, so the OS picks a free port per connection, and read the actual port back from each connection's response.

In another terminal:

```bash
telnet 127.0.0.1 2424
```

### Watching with `telnet-watch.sh`

Plain `telnet` works, but it does not reconnect: if the mirror drops (a server restart, or a new connection cycling in) you have to notice and reconnect by hand. `examples/telnet-watch/telnet-watch.sh` wraps `telnet` with a poll-and-reconnect loop, so it's meant for longer working sessions where you'd rather leave a terminal watching than babysit it.

Point it at a raw host and port, or at a named shortcut from its editable `case` statement — the script ships with a `serial` shortcut for this server's default mirror port:

```bash
./examples/telnet-watch/telnet-watch.sh serial          # shortcut for localhost:2424
./examples/telnet-watch/telnet-watch.sh 127.0.0.1 2424  # equivalent, spelled out
```

See [examples/telnet-watch/README.md](examples/telnet-watch/README.md) for the full quick start, including the `SERIAL_MCP_MIRROR_TCP_PORT=0` case, and how it tells a deliberate quit apart from a dropped connection.

Since this script always connects with a real `telnet` binary, you will usually also want `SERIAL_MCP_MIRROR_TCP_TELNET=1` on the server — see the next section.

### Telnet double-echo

A real telnet client echoes what you type in its own window. The device on the other end often echoes the same keystrokes back too. Without any negotiation, you see each character twice.

Set `SERIAL_MCP_MIRROR_TCP_TELNET=1` to fix this: the server tells the client it will handle echoing, so the client's local echo turns off. This also strips telnet's own protocol bytes out of the mirrored stream so they never reach the serial device. Turn it on only for real telnet clients — a plain socket tool like `nc` does not expect these bytes and does not need it.

```bash
claude mcp add serial \
  -e SERIAL_MCP_MIRROR=rw \
  -e SERIAL_MCP_MIRROR_TRANSPORT=tcp \
  -e SERIAL_MCP_MIRROR_TCP_TELNET=1 \
  -- serial_mcp
```

### Modes

| Mode | Behavior |
|---|---|
| `off` | No mirror (default). Only the MCP server can access the port. |
| `ro` | External tools see all serial data but cannot write to the device. |
| `rw` | External tools can both see data and write to the device. |

### Platform notes

The PTY transport needs `os.openpty()`. macOS and Linux have this function; Windows does not, and has no way to create a virtual COM port on its own. If you set `SERIAL_MCP_MIRROR_TRANSPORT=pty` on Windows anyway, the server logs a warning and turns off the mirror.

**The TCP transport works everywhere, Windows included.** Use it if you need mirroring on Windows. It also handles a dropped and reconnected client better than PTY: a new connection simply replaces the old one, so a plain poll-and-reconnect script gets a clean mirror every time, with nothing special to handle on the client side.

---

## Try without an agent

You can test the server interactively with the [MCP Inspector](https://github.com/modelcontextprotocol/inspector). You do not need Claude or another agent:

```bash
npx @modelcontextprotocol/inspector python -m serial_mcp_server
```

Open the URL with the auth token shown in the terminal output. The Inspector gives you a web UI to call any tool and see the responses in real time.


---

## Known limitations

- **Single-client only.** The server handles one MCP session at a time (stdio transport). Multi-client transports (HTTP/SSE) may be added later.
- **Exclusive access.** Without mirroring enabled, the MCP server must own the serial port exclusively.

---

## Safety

This server connects an AI agent to real hardware. That is the point. It also means the risk is higher than with pure-software tools.

**Plugins run arbitrary code.** When plugins are on, the agent can create and run Python code on your machine with full server privileges. Review agent-generated plugins before you load them. Use `SERIAL_MCP_PLUGINS=name1,name2` to allow only specific plugins, instead of `all`.

**Writes affect real devices.** A bad command sent to a serial device can cause unexpected behavior, disrupt other connected systems, or damage hardware. For example, it could wipe flash, start bootloader mode, or trigger actuators. Think about what the agent can reach.

**Use tool approval with care.** When your MCP client asks you to approve a tool call, decide whether to allow it once or every time. "Always allow" is convenient, but it lets the agent repeat that action without asking again.

This software is provided as-is under the MIT License. You are responsible for what the agent does with your hardware.

---

## License

This project is licensed under the MIT License. See [LICENSE](https://github.com/trgeuy/serial-mcp-server/blob/main/LICENSE) for details.

## Acknowledgements

This project is built on the [pyserial](https://github.com/pyserial/pyserial) library. pyserial handles serial communication in Python on macOS, Windows, and Linux.
