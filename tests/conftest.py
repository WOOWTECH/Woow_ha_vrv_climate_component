"""Shared pytest fixtures."""
from __future__ import annotations

import socket as _socket

import pytest

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
    """Re-enable real sockets for tests marked `integration` (bench gateway).

    `pytest-homeassistant-custom-component` blocks socket.socket and restricts
    socket.socket.connect to 127.0.0.1 by default. Integration tests need to
    talk to the bench Modbus gateway at 192.168.2.20.
    """
    if request.node.get_closest_marker("integration"):
        _socket.socket = _TRUE_SOCKET
        _socket.socket.connect = _TRUE_CONNECT
    yield
