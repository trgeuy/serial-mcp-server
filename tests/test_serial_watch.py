"""serial-watch: argument parsing, and one watch cycle against a local socket (connect, bytes, end, Ctrl-C)."""

import socket
import threading

import pytest

from serial_mcp_server import serial_watch


def test_parse_args_defaults_to_the_servers_mirror_port():
    assert serial_watch.parse_args([]) == ("localhost", 2424)


def test_parse_args_port_and_host_port():
    assert serial_watch.parse_args(["5000"]) == ("localhost", 5000)
    assert serial_watch.parse_args(["10.0.0.2", "2424"]) == ("10.0.0.2", 2424)


def test_parse_args_rejects_a_name():
    # altairsim's mirror-watch.sh takes names (altairsim); serial-watch takes only ports, by design.
    with pytest.raises(ValueError, match='"altairsim" is not a port number'):
        serial_watch.parse_args(["altairsim"])


def test_main_bad_port_exits_1(capsys):
    assert serial_watch.main(["x"]) == 1
    assert "Usage: serial-watch [port | host port]" in capsys.readouterr().err


def test_watch_shows_bytes_then_waits(monkeypatch, capsysbinary):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        c, _ = srv.accept()
        c.sendall(b"A0>DIR\r\n")
        c.close()
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    calls = []

    def fake_sleep(_):
        calls.append(1)
        if len(calls) >= 2:   # after the connection ended and one failed retry: stop as Ctrl-C would
            raise KeyboardInterrupt

    monkeypatch.setattr(serial_watch.time, "sleep", fake_sleep)
    assert serial_watch.main(["127.0.0.1", str(port)]) == 0
    out = capsysbinary.readouterr().out
    assert f"Watching 127.0.0.1:{port}. Press Ctrl-C to stop.".encode() in out
    assert f"Connected to 127.0.0.1:{port}.".encode() in out
    assert b"A0>DIR\r\n" in out
    assert b"The connection ended. Waiting for the mirror to come back..." in out
    assert out.rstrip().endswith(b"Stopped watching.")
