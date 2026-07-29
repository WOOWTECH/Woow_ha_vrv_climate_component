"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture
def no_modbus_retry_sleep(monkeypatch):
    """Zero out pymodbus retry sleeps in tests that need it (opt-in)."""
    async def _sleep(*_args, **_kwargs):
        return None

    monkeypatch.setattr("asyncio.sleep", _sleep)
