# Concepts

This page explains how the Serial MCP server works. It also explains how the pieces connect.

---

## How the agent interacts with devices

The server gives an AI agent, such as Claude, a set of serial tools over the MCP protocol. The agent uses these tools to talk to real hardware. It lists ports, opens connections, sends commands, and reads responses.

Everything is **stateful**. Connections stay open across tool calls. The agent does not need to reopen the port for each operation.

```
┌─────────────┐       stdio/MCP        ┌──────────────────┐      serial       ┌──────────┐
│  AI Agent   │ ◄────────────────────► │ Serial MCP Server │ ◄──────────────► │  Device  │
│ (Claude etc)│   structured JSON      │  (this project)   │    pyserial      │          │
└─────────────┘                        └──────────────────┘                   └──────────┘
```

The agent sees tools such as `serial.open`, `serial.write`, and `serial.readline`. It calls a tool and gets structured JSON back. It uses this JSON to decide what to do next.

---

## Security model

Plugins can run any code, so they are opt-in:

| `SERIAL_MCP_PLUGINS` | Effect |
|---|---|
| *(unset)* | Plugins are off. The server does not load or find any plugin. |
| `all` | The server loads all plugins in `.serial_mcp/plugins/`. |
| `name1,name2` | The server loads only the named plugins. |

The agent cannot bypass these flags. It can use only the tools the server exposes. The server enforces the policy.

The server enforces path containment for all file operations:
- **Plugins.** Must be inside `.serial_mcp/plugins/`.
- **Specs.** Must be inside the project directory, the parent of `.serial_mcp/`.
- **Traces.** Always write to `.serial_mcp/traces/trace.jsonl`. You cannot change this path.

The agent is not a trusted principal. The server enforces every safety boundary, even when the agent tries to bypass it.


---

## Protocol specs: teaching the agent about your device

Specs are markdown files. They describe a serial device's protocol: connection settings, message format, commands, and multi-step flows.

```
.serial_mcp/
  specs/
    my-device.md      # protocol documentation
```

The agent reads specs to learn what a device can do. Without a spec, the agent can still open a port and exchange data. But it will not know what commands to send or what the responses mean.

### How specs help the agent

```
Without spec:                         With spec:
  "I opened /dev/ttyUSB0 at 115200.    "This is the GPS module. It uses
   I can send bytes but I don't          9600 baud, NMEA 0183 format.
   know what the device expects."        $GPGGA sentences contain lat/lon.
                                         Send $PMTK314,0,1,0,0,0,0*29
                                         to enable RMC-only output."
```

### Creating a spec

Tell the agent about your device's protocol. You can paste a datasheet, give a link to the docs, or describe the commands in chat. The agent creates the spec file, registers it, and uses it in future sessions.

You can also write specs by hand. They are markdown files with a small YAML header.

### How the agent uses specs

After the agent opens a connection, it can check for registered specs. It can attach a matching spec and use it through the session. It looks up commands, expected responses, and multi-step flows as needed.

Specs are freeform markdown. The agent reads them and reasons about their content. There is no fixed schema to follow, so specs can change and grow along with your protocol.

### Beyond the agent

Specs are not only for the agent. They are structured protocol documentation that lives in your repository. If you design a new serial protocol, specs from agent sessions can become the base for official protocol docs. They record what the agent found, tested, and verified through real device interaction.

---

## Plugins: giving the agent shortcut tools

Plugins add device-specific tools to the server. Instead of building write and read sequences by hand, the agent calls a plugin. A plugin gives high-level actions, such as `gps.get_position` or `sensor.read_temp`.

```
.serial_mcp/
  plugins/
    gps.py           # adds gps.* tools
    sensor.py        # adds sensor.* tools
```

### What a plugin provides

```python
TOOLS = [...]       # Tool definitions the agent can call
HANDLERS = {...}    # Implementation for each tool
META = {...}        # Optional: matching hints (device name patterns, description)
```

### How the agent uses plugins

After the agent opens a connection, it checks `serial.plugin.list`. Each plugin has metadata. This metadata helps the agent decide if the plugin fits the device:

```json
{
  "name": "gps",
  "tools": ["gps.get_position", "gps.configure_output"],
  "meta": {
    "description": "NMEA GPS module plugin",
    "device_name_contains": "GPS"
  }
}
```

### AI-authored plugins

The agent can also **create** plugins. It uses `serial.plugin.template` to generate a skeleton. It fills in the code based on the device spec and saves the file to `.serial_mcp/plugins/`. After a server restart, or a hot-reload, the new tools become available. Review generated plugins before you enable them in sensitive environments.

This is the core loop. The agent explores a device and writes a plugin for it. Future sessions then get shortcut tools.

### Beyond the agent

Plugin code runs with the same privileges as the MCP server process. You can use it as a starting point for standalone test scripts, CLI tools, or production libraries. The agent writes the first draft based on the device spec. You then refine it into what you need.

---

## How specs and plugins connect

Specs and plugins serve different roles:

| | Spec | Plugin |
|---|---|---|
| **What** | Documentation | Code |
| **Purpose** | Teach the agent what the device can do | Give the agent shortcut tools |
| **Format** | Freeform markdown | Python module |
| **Required?** | No. The agent can still explore with raw tools. | No. The agent can use raw serial tools. |
| **Bound to** | A connection (via `serial.spec.attach`) | Global (all connections) |

They work together:

```
                    ┌──────────────────┐
                    │  Protocol Spec   │──── "What can this device do?"
                    │  (markdown)      │     Agent reads and reasons
                    └────────┬─────────┘
                             │
                     agent reasons about
                     the spec, or creates
                             │
                    ┌────────▼─────────┐
                    │     Plugin       │──── "Shortcut tools for this device"
                    │  (Python module) │     Agent calls directly
                    └──────────────────┘
```

A plugin does not need a spec. A spec does not need a plugin. But when both exist for a device, the agent gets the best of both: deep protocol knowledge from the spec, and fast actions from the plugin.

---

## Mirror: watch or share a connection with an external tool

When the MCP server opens a serial port, it has exclusive access. No other tool can read from it. Mirroring solves this. It creates a second, external-facing copy of the same byte stream. An external tool connects to that copy and sees exactly what the server sees.

There are two transports: PTY, a virtual serial device file, and TCP, a plain network socket. Choose one with `SERIAL_MCP_MIRROR_TRANSPORT`.

### Architecture

Every open connection has a background reader thread and a thread-safe buffer. All reads go through this buffer, whether mirroring is on or off.

```
Always (all platforms):

  serial port → background reader thread → SerialBuffer → MCP tools read from here

Mirror on, PTY transport (macOS/Linux only):

  background reader thread also → PTY master → PTY slave (external tool reads here)
  PTY slave (rw mode) → PTY master → background reader thread → serial port

Mirror on, TCP transport (all platforms):

  background reader thread also → TCP client socket (external tool reads here)
  TCP client socket (rw mode) → background reader thread → serial port
```

### Modes (apply to either transport)

| Mode | Data flow |
|---|---|
| `off` | No mirror. Serial data goes to the buffer only. |
| `ro` | The server copies serial data to both the buffer and the mirror. The external tool can read the data but cannot write to the device. |
| `rw` | This mode does everything `ro` does. It also forwards data from the external tool to the real serial port. A write lock stops MCP writes and mirror writes from mixing together. |

### Choosing a transport

| | PTY | TCP |
|---|---|---|
| **Platforms** | macOS/Linux only | All platforms, including Windows |
| **Why the difference** | PTY needs `os.openpty()`. Windows has no equivalent function and no way to create a virtual COM port on its own. | A plain socket. It works the same on every platform. |
| **Client sees** | A real device file (`/dev/ttys004`, or a stable symlink like `/tmp/serial-mcp0`) | A `host:port` to connect to (telnet, or any raw TCP client) |
| **Reconnecting** | The client owns one PTY for the life of the mirror. If the mirror drops, most terminal apps do not notice when the device returns. They do not retry on their own. | Each new connection replaces the previous one. A simple poll-and-reconnect script, for example one that retries `connect()` until the port answers, gets a clean, working mirror every time. It needs no special handling. |
| **Use when** | An external tool needs a device file, for example `screen` or `minicom`. | Anything else. This includes watching a device from a different machine, or when you want a setup that reconnects easily. |

### Configuration

```
SERIAL_MCP_MIRROR=off                     # off (default), ro, or rw
SERIAL_MCP_MIRROR_TRANSPORT=pty           # pty (default) or tcp

# PTY transport:
SERIAL_MCP_MIRROR_LINK=/tmp/serial-mcp    # symlink base path (default when mirror is enabled)

# TCP transport:
SERIAL_MCP_MIRROR_TCP_HOST=127.0.0.1      # bind address (default: loopback only)
SERIAL_MCP_MIRROR_TCP_PORT=2424           # bind port (default: 2424; set to 0 for an OS-picked ephemeral port)
```

Each connection gets its own mirror. For PTY, this means a numbered symlink: `/tmp/serial-mcp0`, `/tmp/serial-mcp1`, and so on. Override the base path with `SERIAL_MCP_MIRROR_LINK`. For TCP, a fixed port fits only one bound socket, so only one connection can hold it at a time. To mirror a second connection at the same time, use a different port, or set `SERIAL_MCP_MIRROR_TCP_PORT=0` so the OS picks a free port for each connection. Either way, `serial.open`'s response, and `serial.connection_status`, report the actual bound host and port under `mirror.tcp_host` and `mirror.tcp_port`.

### Platform

PTY mirroring needs macOS or Linux. If you set `SERIAL_MCP_MIRROR_TRANSPORT=pty` on Windows, the server logs a warning and turns off the mirror. The buffer and background reader still work normally. **TCP mirroring works on Windows too.** If you need mirroring on Windows, use `SERIAL_MCP_MIRROR_TRANSPORT=tcp`.

### When to use each mode

- **`off`.** The default. Use this when the MCP server is the only tool that talks to the device.
- **`ro`.** Use this when you want to watch traffic in another terminal, for example `screen`, `minicom`, a logic analyzer, or plain `telnet` for the TCP transport, while the agent drives the device.
- **`rw`.** Use this when you need two-way access from both the agent and an external tool at the same time. Both can write to the device, so plan for this. `paced.exclusive_begin` and `paced.exclusive_end` (see Paced Writes in the tools reference) can pause the external tool's writes during a multi-call agent sequence, without giving up `rw` mode the rest of the time.

---

## The agent's decision flow

After the agent opens a connection, it follows this flow:

```
Open serial port
       │
       ▼
Check serial.spec.list ──── matching spec? ──── yes ──► serial.spec.attach
       │                                                       │
       │ no                                                    │
       ▼                                                       ▼
Check serial.plugin.list ◄──────────────────────── Check serial.plugin.list
       │                                                       │
       │                                                       ▼
       ▼                                             Present options:
  matching plugin? ─── yes ──► use plugin tools       • use plugin tools
       │                                              • follow spec manually
       │ no                                           • extend plugin
       ▼                                              • create new plugin
  Ask user / explore
  with raw serial tools
```

The tool descriptions guide it through each step.
