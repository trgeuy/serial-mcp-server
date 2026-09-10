#!/bin/bash
#
# telnet-watch.sh — monitor a TCP port and maintain a telnet session to it
#
# Written for the TCP mirror transport (SERIAL_MCP_MIRROR_TRANSPORT=tcp, see
# docs/concepts.md's Mirror section) — point it at the host/port serial.open
# reports back under mirror.tcp_host/mirror.tcp_port (or a named shortcut,
# see below), and it stays attached for as long as you want to watch,
# reconnecting on its own if the mirror drops (server restart, a new
# connection cycling in, etc.). Nothing about the polling/reconnect logic is
# specific to this project — it works with any plain TCP service you'd
# normally point telnet at.
#
# Usage:
#   ./telnet-watch.sh [target|host] [port]
#
#   Named targets (no port needed) — edit the case statement below to match
#   your own setup; these two are examples from a project that pairs this
#   server with the altairsim emulator:
#     ./telnet-watch.sh altairsim   -> localhost:2323 (altairsim's own --mirror socket:2323)
#     ./telnet-watch.sh serial      -> localhost:2424 (serial_mcp's SERIAL_MCP_MIRROR_TCP_PORT default)
#
#   Or raw host/port, for anything else:
#     ./telnet-watch.sh 127.0.0.1 54321
#
#   No arguments defaults to "serial" (localhost:2424) — serial_mcp's own
#   default TCP mirror port. Edit the fallback below if you'd rather default
#   to something else, or require explicit args.
#
# Behavior:
#   - Polls <host>:<port> using bash's built-in /dev/tcp (no subprocess spawn,
#     so it's cheap to poll very fast)
#   - When the port is open, launches `telnet` to it
#   - When telnet exits because the *remote* dropped it (server restarted,
#     crashed, etc.), it goes back to polling and reconnects automatically
#     once the port is open again
#   - When telnet exits because *you* quit it deliberately (Ctrl-] then
#     `quit`), it asks whether to end the watch session instead of silently
#     reconnecting you right back in -- see note below on how it tells the
#     two cases apart
#   - Only logs on state changes (waiting -> connecting -> ended), plus a
#     quiet in-place heartbeat while waiting, so tight polling doesn't flood
#     your terminal
#   - Ctrl-C at any point exits the script entirely
#
# Note on telling "you quit" apart from "the remote dropped you": telnet's
# own exit code distinguishes these cleanly. Deliberately quitting (Ctrl-]
# then `quit`) exits 0 with "Connection closed." (no "by foreign host"); the
# remote closing the connection exits nonzero with "Connection closed by
# foreign host." Without this check, a deliberate quit looks identical to a
# dropped connection and the script would just silently reconnect you right
# back into the same session, with no way to actually stop watching short of
# Ctrl-C'ing the whole script.
#
# Note on running telnet in the foreground (not backgrounded): backgrounding
# it (`telnet ... &` + `wait`) made every connection drop within a fraction
# of a second of "Connected" in testing -- exact mechanism not pinned down,
# but reliably fixed by running it in the foreground instead. If Ctrl-C
# during an active session doesn't cleanly kill telnet for you, that's the
# tradeoff -- telnet may catch SIGINT itself and drop to its own "telnet>"
# prompt (Ctrl-] does this too); `quit` there gets you out.

set -u

# Named targets, resolved with a case statement rather than an associative
# array -- macOS ships bash 3.2 (pre-GPLv3), which has no `declare -A`.
case "${1:-}" in
    altairsim)
        HOST="localhost"; PORT="2323"
        ;;
    serial)
        HOST="localhost"; PORT="2424"
        ;;
    *)
        HOST="${1:-localhost}"
        PORT="${2:-2424}"
        ;;
esac
POLL_INTERVAL="${POLL_INTERVAL:-0.1}"   # seconds between port checks
SETTLE_DELAY="${SETTLE_DELAY:-0.15}"    # brief pause after port opens before connecting,
                                         # so the server has time to finish binding/listening
HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-1}"  # seconds between heartbeat dots while waiting

cleanup() {
    echo
    echo "Exiting."
    exit 0
}
trap cleanup INT TERM TSTP

log() {
    printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

port_is_open() {
    # Bash's built-in /dev/tcp pseudo-device — a plain TCP connect test with
    # no external process spawn, cheap enough to poll many times a second.
    (exec 3<>"/dev/tcp/$HOST/$PORT") 2>/dev/null
    local result=$?
    exec 3>&- 2>/dev/null
    exec 3<&- 2>/dev/null
    return $result
}

log "Watching $HOST:$PORT — will connect via telnet whenever it's reachable, and reconnect automatically if it drops."

last_heartbeat=0
while true; do
    if port_is_open; then
        sleep "$SETTLE_DELAY"   # let the server finish standing up before attaching
        log "Port $PORT on $HOST is open — connecting..."
        telnet "$HOST" "$PORT"
        telnet_exit=$?

        if [[ $telnet_exit -eq 0 ]]; then
            log "You quit telnet."
            read -r -p "End this watch session? [y/N] " answer
            case "$answer" in
                [Yy]*) cleanup ;;
                *) log "Reconnecting..." ;;
            esac
        else
            log "Session ended (server restarted or dropped the connection). Watching for it to come back..."
        fi
        last_heartbeat=0
    else
        now=$(date +%s)
        if (( now - last_heartbeat >= HEARTBEAT_INTERVAL )); then
            printf '.'
            last_heartbeat=$now
        fi
        sleep "$POLL_INTERVAL"
    fi
done
