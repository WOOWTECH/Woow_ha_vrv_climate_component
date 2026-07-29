"""Shared pytest fixtures."""
from __future__ import annotations

import socket as _socket

import pytest

# The real, un-guarded socket class and connect method, captured before
# ``pytest-homeassistant-custom-component`` / ``pytest-socket`` install any
# guards. These are what we swap in for integration tests.
_TRUE_SOCKET = _socket.socket
_TRUE_CONNECT = _socket.socket.connect


@pytest.fixture
def no_modbus_retry_sleep(monkeypatch):
    """Zero out pymodbus retry sleeps in tests that need it (opt-in)."""
    async def _sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr("asyncio.sleep", _sleep)


@pytest.fixture(autouse=True)
def _enable_socket_for_integration(request):
    """Allow real network for @pytest.mark.integration tests only.

    ``pytest-homeassistant-custom-component`` blocks ``socket.socket`` and
    restricts ``socket.socket.connect`` to 127.0.0.1 by default. Integration
    tests need to talk to the bench Modbus gateway at 192.168.2.20, so we
    swap in the real class + connect on setup and restore whatever guards
    were installed on teardown. Without the teardown, a preceding
    integration test would leak network access into later unit tests.
    """
    if not request.node.get_closest_marker("integration"):
        yield
        return

    # Snapshot whatever guards are currently installed so we can put them
    # back exactly as they were.
    saved_socket_cls = _socket.socket
    saved_connect = _socket.socket.connect

    _socket.socket = _TRUE_SOCKET
    _socket.socket.connect = _TRUE_CONNECT
    try:
        yield
    finally:
        _socket.socket = saved_socket_cls
        _socket.socket.connect = saved_connect
