# mirror-watch.ps1 -- watch a console mirror (altairsim, serial-mcp) in a
# PowerShell window.
#
# Usage:
#   .\mirror-watch.ps1                 watch localhost on the default port
#   .\mirror-watch.ps1 port            watch localhost:port
#   .\mirror-watch.ps1 host port       watch a mirror on another computer
#   .\mirror-watch.ps1 altairsim       localhost:2323 (altairsim --mirror socket:2323)
#   .\mirror-watch.ps1 serial          localhost:2424 (serial-mcp's TCP mirror default)
#
# Start the mirror first, for example altairsim with  --mirror socket:2323?ro
# Then run this script in a second window. It shows everything the
# machine prints. Press Ctrl-C to stop watching.
#
# Windows does not run script files by default. To run this one, one time:
#   powershell -ExecutionPolicy Bypass -File .\mirror-watch.ps1
# To run scripts directly from now on (your account only), run once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# and, if you downloaded this file with a web browser, also run once:
#   Unblock-File .\mirror-watch.ps1
#
# The script only watches. It does not send what you type. To type into the
# machine through a read-write mirror, use a full terminal emulator.
#
# The script needs nothing but PowerShell: it connects to the port itself,
# so you do not need a telnet client (Windows does not install one). It
# shows the bytes as they arrive, so do not turn on telnet negotiation on the
# server (serial-mcp's SERIAL_MCP_MIRROR_TCP_TELNET). Those bytes show as junk.
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
# while the machine runs, look for another watcher window that still holds
# the mirror.
#
# serial-mcp's TCP mirror also accepts one watcher at a time. A second
# watcher gets the line "another client is already connected", and its
# connection ends. This script then tries again every second. If you see
# that line repeat, close the other watcher window.

$DefaultPort = 2424   # the port to watch when you give no port

# Read the arguments as text first, so a wrong one stops here with a clear message.
if ($args.Count -ge 1 -and $args[0] -eq 'altairsim') {
    $HostName = 'localhost'; $PortText = '2323'
} elseif ($args.Count -ge 1 -and $args[0] -eq 'serial') {
    $HostName = 'localhost'; $PortText = '2424'
} elseif ($args.Count -ge 2) {
    $HostName = [string]$args[0]; $PortText = [string]$args[1]
} elseif ($args.Count -eq 1) {
    $HostName = 'localhost'; $PortText = [string]$args[0]
} else {
    $HostName = 'localhost'; $PortText = [string]$DefaultPort
}

if ($PortText -notmatch '^[0-9]+$') {
    [Console]::Error.WriteLine("mirror-watch: `"$PortText`" is not a port number.")
    [Console]::Error.WriteLine("Usage: .\mirror-watch.ps1 [port | host port | altairsim | serial]")
    exit 1
}
$Port = [int]$PortText

$RetryDelayMs = 1000   # time between tries while the mirror is not there

function Say([string]$Text) {
    # Make the line first. Inside Write( ), a comma would split the arguments.
    $Line = "`n[{0}] {1}`n" -f (Get-Date -Format 'HH:mm:ss'), $Text
    [Console]::Write($Line)
}

# Show each byte as one character, with no change. The machine sends plain
# bytes, not text in a Windows code page.
$Latin1 = [System.Text.Encoding]::GetEncoding(28591)
$Buffer = New-Object byte[] 4096
$Client = $null

Say "Watching ${HostName}:${Port}. Press Ctrl-C to stop."

# The loop waits in short steps, not in one long blocking call, because
# PowerShell does not act on Ctrl-C until a blocking call returns.
try {
    $WaitingShown = $false
    while ($true) {
        $Client = New-Object System.Net.Sockets.TcpClient
        $Connected = $false
        try {
            $Attempt = $Client.BeginConnect($HostName, $Port, $null, $null)
            if ($Attempt.AsyncWaitHandle.WaitOne(2000)) {
                $Client.EndConnect($Attempt)
                $Connected = $true
            }
        } catch {
            $Connected = $false
        }

        if ($Connected) {
            Say "Connected to ${HostName}:${Port}."
            $Stream = $Client.GetStream()
            $Socket = $Client.Client
            try {
                while ($true) {
                    if ($Socket.Available -gt 0) {
                        $Count = $Stream.Read($Buffer, 0, $Buffer.Length)
                        if ($Count -le 0) { break }
                        [Console]::Write($Latin1.GetString($Buffer, 0, $Count))
                    } elseif ($Socket.Poll(50000, [System.Net.Sockets.SelectMode]::SelectRead) -and
                              $Socket.Available -eq 0) {
                        # Readable but no data: the other end closed the connection.
                        break
                    }
                }
            } catch {
                # A reset connection can come here as an error. It ends the session too.
            }
            $Client.Close()
            Say "The connection ended. Waiting for the mirror to come back..."
            $WaitingShown = $true
        } else {
            $Client.Close()
            if (-not $WaitingShown) {
                Say "Nothing on ${HostName}:${Port} yet. Waiting..."
                $WaitingShown = $true
            } else {
                [Console]::Write('.')
            }
        }
        Start-Sleep -Milliseconds $RetryDelayMs
    }
} finally {
    # Ctrl-C comes here.
    if ($Client) { $Client.Close() }
    Say "Stopped watching."
}
