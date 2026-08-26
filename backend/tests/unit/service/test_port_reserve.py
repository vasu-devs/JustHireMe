"""Port reservation closes the TOCTOU handshake race (Tier-0 fix 0.5)."""
import socket

import main


def test_reserve_socket_returns_bound_port():
    s = main._reserve_socket()
    try:
        host, port = s.getsockname()
        assert host == "127.0.0.1"
        assert 1 <= port <= 65535
    finally:
        s.close()


def test_reserved_port_is_exclusively_held():
    """While we hold the socket, nothing else can bind the same port — that's
    what makes announcing the port to the UI before serving safe."""
    s = main._reserve_socket()
    try:
        port = s.getsockname()[1]
        clash = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            raised = False
            try:
                clash.bind(("127.0.0.1", port))
            except OSError:
                raised = True
            assert raised, "a second bind to the reserved port should fail"
        finally:
            clash.close()
    finally:
        s.close()


def test_reserve_specific_port_roundtrips():
    # Pick a free port, release it, then reserve that exact number.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    wanted = probe.getsockname()[1]
    probe.close()
    s = main._reserve_socket(wanted)
    try:
        assert s.getsockname()[1] == wanted
    finally:
        s.close()
