"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Prevent pymodbus retry sleeps from stalling tests."""
    async def _sleep(_):
        return None

    monkeypatch.setattr("asyncio.sleep", _sleep)
