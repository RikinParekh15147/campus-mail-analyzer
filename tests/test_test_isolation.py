import socket

import pytest

from campusmail.google import GoogleConnection


def test_test_vault_is_in_memory_and_connections_start_disconnected(isolated_services):
    connection = GoogleConnection("fixture-owner", "gmail")
    assert connection.vault is isolated_services
    assert connection.status()["connected"] is False
    isolated_services.set_password("campusmail", "fixture-owner:gmail", "fake-value")
    assert connection.status()["connected"] is True


def test_external_network_is_blocked_but_local_socketpair_works():
    with socket.socket() as connection:
        with pytest.raises(AssertionError, match="fake provider"):
            connection.connect(("192.0.2.1", 443))
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"local")
        assert right.recv(5) == b"local"
