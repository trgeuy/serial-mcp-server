# mirror-watch

Two small scripts that let you watch the TCP mirror (`SERIAL_MCP_MIRROR_TRANSPORT=tcp`; see the Mirror section in [docs/concepts.md](../../docs/concepts.md)) in a second window, while the agent drives the device:

| Script | Runs on | Needs |
|---|---|---|
| `mirror-watch.sh` | macOS, Linux | bash only |
| `mirror-watch.ps1` | Windows | PowerShell only |

Each script connects to the mirror's port itself, so you do not need `telnet` or `nc`. A clean macOS has no `telnet`, and Windows does not install a telnet client.

The scripts wait for the mirror if it is not there yet, show the output while connected, and connect again on their own when the mirror comes back after a drop. A mirror drops when the server restarts, or when a new client takes its place. Leave a window open for a full working session, and you never have to reconnect by hand.

## Quick start

The TCP mirror uses a fixed port by default: `SERIAL_MCP_MIRROR_TCP_PORT`, default `2424`. The scripts use the same default:

```bash
./examples/mirror-watch/mirror-watch.sh            # localhost:2424
```

```powershell
powershell -ExecutionPolicy Bypass -File .\examples\mirror-watch\mirror-watch.ps1
```

Press Ctrl-C to stop watching.

### Running a script on Windows

By default, Windows does not run PowerShell script files. There are two ways to run this one:

- **One time.** Start it with `powershell -ExecutionPolicy Bypass -File`, as above. This changes no setting.
- **Every time, for your account.** Run this once:

  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```

  After that, `.\examples\mirror-watch\mirror-watch.ps1` runs directly. This setting runs scripts that are on your computer, but blocks scripts downloaded from the internet that are not signed. If you downloaded the file with a web browser (not with `git clone`), Windows marks it as downloaded. Remove that mark once:

  ```powershell
  Unblock-File .\examples\mirror-watch\mirror-watch.ps1
  ```

## Arguments

Both scripts take the same arguments:

| Arguments | Watches |
|---|---|
| (none) | `localhost:2424` |
| `port` | `localhost:port` |
| `host port` | `host:port`, for a mirror on another computer |
| `serial` | `localhost:2424`, this server's default mirror port |
| `altairsim` | `localhost:2323`, the console mirror of [altairsim](https://github.com/deltecent/altairsim) (`--mirror socket:2323`), a separate Altair 8800 simulator |

To change the default port, or to add a shortcut of your own, edit the script. The default port is set on one line near the top (`DEFAULT_PORT` in the `.sh` file, `$DefaultPort` in the `.ps1` file).

If you mirror more than one connection at the same time, set `SERIAL_MCP_MIRROR_TCP_PORT=0`. Then the OS gives each connection its own free port. Read the port from the `serial.open` response:

```json
{ "mirror": { "transport": "tcp", "tcp_host": "127.0.0.1", "tcp_port": 54321, "mode": "ro" } }
```

```bash
./examples/mirror-watch/mirror-watch.sh 54321
```

## Watch only

The scripts only watch. They do not send what you type to the device. Use them with a `ro` mirror, or to watch an `rw` mirror.

To type into the device through an `rw` mirror, use a full terminal emulator, or plain `telnet` with `SERIAL_MCP_MIRROR_TCP_TELNET=1` (see the Telnet double-echo section in [docs/concepts.md](../../docs/concepts.md)).

## Leave telnet negotiation off

The scripts show each byte as it arrives. If `SERIAL_MCP_MIRROR_TCP_TELNET=1` is set on the server, the server sends telnet negotiation bytes to each new client, and the scripts show them as a few junk characters. Leave that setting off (the default) when you use these scripts.

## One watcher at a time

This server gives the mirror to the newest client. If you open a second watch window, it takes the mirror from the first window. One second later the first window connects again and takes the mirror back. So the two windows take the mirror from each other again and again. Keep only one watch window open for each mirror.

altairsim's mirror works the other way. It keeps the first watcher, and a second one waits in a queue. altairsim also accepts a watcher only while the simulated machine runs, so a window can show "Connected" and nothing more until the machine runs. If an altairsim watch window stays empty while the machine runs, look for another watcher that still holds the mirror (a window that is open, or one stopped with Ctrl-Z).

The scripts make one connection at a time. They do not test the port with an extra connection first, because in altairsim's queue an extra connection would push out the real one.
