"""Portable defaults: fake credentials and block external network connections."""

import socket

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-research",
        action="store_true",
        default=False,
        help="Run checks requiring the separately installed private research inputs",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-research"):
        return
    portable, research = [], []
    for item in items:
        (research if item.get_closest_marker("research") else portable).append(item)
    items[:] = portable
    config.hook.pytest_deselected(items=research)


class MemoryVault:
    def __init__(self):
        self.values = {}

    def get_password(self, service, key):
        return self.values.get((service, key))

    def set_password(self, service, key, value):
        self.values[service, key] = value

    def delete_password(self, service, key):
        self.values.pop((service, key), None)


@pytest.fixture(autouse=True)
def isolated_services(monkeypatch, tmp_path):
    from campusmail import google
    from campusmail import application
    import keyring

    vault = MemoryVault()
    # Application tests must not accidentally load a developer's private model bundle.
    monkeypatch.setattr(application, "PROJECT", tmp_path / "empty-project")
    monkeypatch.setattr(google, "default_vault", lambda: vault)
    for operation in ("get_password", "set_password", "delete_password"):
        monkeypatch.setattr(keyring, operation, getattr(vault, operation))

    def no_network(*args, **kwargs):
        raise AssertionError(
            "Unit tests must inject a fake provider; network is disabled"
        )

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def local_only(operation):
        def connect(sock, address):
            # Windows emulates socketpair with loopback TCP for asyncio's self-pipe.
            # Preserve local IPC without permitting external provider connections.
            if sock.family == getattr(socket, "AF_UNIX", None) or (
                isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1")
            ):
                return operation(sock, address)
            return no_network()

        return connect

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", local_only(original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", local_only(original_connect_ex))
    return vault
