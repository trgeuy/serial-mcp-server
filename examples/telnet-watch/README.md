# telnet-watch.sh

A small poll-and-reconnect wrapper around `telnet`, written for the TCP mirror transport (`SERIAL_MCP_MIRROR_TRANSPORT=tcp` — see the Mirror section in [docs/concepts.md](../../docs/concepts.md)). Point it at the mirror's `host`/`port` and it stays attached for as long as you want to watch, reconnecting automatically whenever the mirror drops — a server restart, or simply a new connection cycling in (the TCP transport replaces the old client rather than refusing the new one, for exactly this reason).

Nothing about it is specific to this project — it works with any plain TCP service you'd normally point `telnet` at.

## Quick start

Open a connection with the mirror enabled:

```
serial.open → { "port": "/dev/ttyUSB0", ... }
```

The response reports where to connect:

```json
{ "mirror": { "transport": "tcp", "tcp_host": "127.0.0.1", "tcp_port": 54321, "mode": "ro" } }
```

Then, in another terminal:

```bash
./telnet-watch.sh 127.0.0.1 54321
```

You'll see the same byte stream the MCP server sees, live. If the connection drops for any reason, `telnet-watch.sh` notices and reattaches on its own — no need to re-run it or guess whether the port has come back yet.

## Why not just run `telnet` directly?

You can — `telnet-watch.sh` only helps with the reconnect case. Plain `telnet` works fine for a single, uninterrupted session. This script exists for the case where the mirror is expected to come and go over a longer working session (the agent closes and reopens the connection, the server restarts, you want to leave a terminal window watching for hours) and you don't want to babysit it.

## Quitting for real

Ctrl-] then `quit` inside telnet ends that one session. The script then asks whether you want to stop watching entirely, since a deliberate quit and the far end just dropping you look identical from telnet's side without that check — say no and it keeps polling, say yes (or just Ctrl-C the script) to actually exit.
