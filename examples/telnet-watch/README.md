# telnet-watch.sh

This is a small poll-and-reconnect wrapper around `telnet`. It is written for the TCP mirror transport (`SERIAL_MCP_MIRROR_TRANSPORT=tcp`; see the Mirror section in [docs/concepts.md](../../docs/concepts.md)). Point it at the mirror's `host` and `port`. It then stays attached for as long as you want to watch, and it reconnects on its own whenever the mirror drops. A mirror can drop for two reasons: the server restarts, or a new connection cycles in. Either way, the script recovers, because the TCP transport always replaces the old client instead of refusing the new one.

The polling and reconnect logic is not specific to this project. It works with any plain TCP service you would normally point `telnet` at. The script also has an editable `case` statement for named shortcuts. For example, `./telnet-watch.sh serial` works instead of typing out `localhost 2424`. The script ships with one example pair, from a project that pairs this server with an Altair 8800 emulator called altairsim. Edit the `case` statement to match your own setup.

## Quick start

By default, the TCP mirror binds a fixed port: `SERIAL_MCP_MIRROR_TCP_PORT`, default `2424`. Once it is configured, you do not need to read the port back from `serial.open` each time:

```bash
./telnet-watch.sh serial          # named shortcut -> localhost:2424
./telnet-watch.sh 127.0.0.1 2424  # equivalent, spelled out
```

If you mirror more than one connection at once, set `SERIAL_MCP_MIRROR_TCP_PORT=0` instead. A fixed port only fits one bound socket, so each connection needs its own port. With `0`, the OS picks a free port for each connection. Read the actual bound port from `serial.open`'s response each time:

```
serial.open → { "port": "/dev/ttyUSB0", ... }
```

```json
{ "mirror": { "transport": "tcp", "tcp_host": "127.0.0.1", "tcp_port": 54321, "mode": "ro" } }
```

```bash
./telnet-watch.sh 127.0.0.1 54321
```

You see the same byte stream the MCP server sees, live. If the connection drops for any reason, `telnet-watch.sh` notices and reattaches on its own. You do not need to re-run it or guess whether the port has come back.

## Double-echo

Real `telnet` echoes what you type in its own window. If the device also echoes the same keystrokes back, you see everything twice. Set `SERIAL_MCP_MIRROR_TCP_TELNET=1` on the server to fix this — see the Telnet double-echo section in [docs/concepts.md](../../docs/concepts.md). This wrapper script does not need any change; the fix lives entirely on the server side.

## Why not just run `telnet` directly?

You can. `telnet-watch.sh` only helps with the reconnect case. Plain `telnet` works fine for a single, uninterrupted session. Use this script when the mirror is expected to come and go over a longer working session, and you do not want to babysit it. For example, the agent may close and reopen the connection, the server may restart, or you may want to leave a terminal window watching for hours.

## Quitting for real

Ctrl-] then `quit` inside telnet ends that one session. Without a check, a deliberate quit and the far end dropping you look identical from telnet's side. So the script then asks whether you want to stop watching entirely. Say no, and it keeps polling. Say yes, or press Ctrl-C, to exit for real.
