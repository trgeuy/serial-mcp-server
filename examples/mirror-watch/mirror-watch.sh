#!/bin/bash
#
# mirror-watch.sh -- watch a console mirror (altairsim, serial-mcp) in a
# terminal window.
#
# Usage:
#   ./mirror-watch.sh                 watch localhost on the default port
#   ./mirror-watch.sh port            watch localhost:port
#   ./mirror-watch.sh host port       watch a mirror on another computer
#   ./mirror-watch.sh altairsim       localhost:2323 (altairsim --mirror socket:2323)
#   ./mirror-watch.sh serial          localhost:2424 (serial-mcp's TCP mirror default)
#
# Start the mirror first, for example altairsim with  --mirror socket:2323?ro
# Then run this script in a second window. It shows everything the
# machine prints. Press Ctrl-C to stop watching.
#
# The script only watches. It does not send what you type. To type into the
# machine through a read-write mirror, use a full terminal emulator.
#
# The script needs nothing but bash: bash itself connects to the port
# (the /dev/tcp feature), so you do not need telnet or nc. It shows the
# bytes as they arrive, so do not turn on telnet negotiation on the server
# (serial-mcp's SERIAL_MCP_MIRROR_TCP_TELNET). Those bytes show as junk here.
#
# What it does:
#   - If the mirror is not there yet, it waits and tries again.
#   - When it connects, it shows the output until the connection ends.
#   - When the connection ends (the server stopped or restarted), it waits
#     for the mirror to come back and connects again.
#
# It makes only one connection at a time and never "tests" the port with
# a second connection. altairsim's mirror accepts one watcher at a time,
# and only while the machine runs. Until then the connection waits in a
# queue that has room for one; an extra test connection fills that place
# and the real connection is refused. So a window that shows "Connected"
# and nothing else is normal until the machine runs. If it stays empty
# while the machine runs, look for another watcher window (one that is
# open, or stopped with Ctrl-Z) that still holds the mirror.

set -u

DEFAULT_PORT=2424   # the port to watch when you give no port

case "${1:-}" in
    altairsim) HOST="localhost"; PORT="2323" ;;
    serial)    HOST="localhost"; PORT="2424" ;;
    *)
        if [[ $# -ge 2 ]]; then
            HOST="$1"; PORT="$2"
        else
            HOST="localhost"; PORT="${1:-$DEFAULT_PORT}"
        fi
        ;;
esac

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
    echo "mirror-watch: \"$PORT\" is not a port number." >&2
    echo "Usage: $0 [port | host port | altairsim | serial]" >&2
    exit 1
fi

RETRY_DELAY=1   # seconds between tries while the mirror is not there

say() {
    printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

trap 'printf "\n"; say "Stopped watching."; exit 0' INT TERM

say "Watching $HOST:$PORT. Press Ctrl-C to stop."

waiting_shown=0
while true; do
    # The braces send bash's own "Connection refused" message to /dev/null.
    # (A 2>/dev/null on the exec line itself comes too late to catch it.)
    if { exec 3<>"/dev/tcp/$HOST/$PORT"; } 2>/dev/null; then
        say "Connected to $HOST:$PORT."
        cat <&3
        exec 3<&-
        say "The connection ended. Waiting for the mirror to come back..."
        waiting_shown=1
    elif [[ $waiting_shown -eq 0 ]]; then
        say "Nothing on $HOST:$PORT yet. Waiting..."
        waiting_shown=1
    else
        printf '.'
    fi
    sleep "$RETRY_DELAY"
done
