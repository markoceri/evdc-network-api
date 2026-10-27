"""Tests for evdc_network_api.async_client."""

from __future__ import annotations

import asyncio

from evdc_network_api.async_client import AsyncEvdcApiClient
from evdc_network_api.client import EvdcApiClient

from .conftest import FakeResponse, FakeSession, load_fixture


def _async_client(session: FakeSession) -> AsyncEvdcApiClient:
    client = EvdcApiClient(email="x@example.com", access_token="token", session=session)  # type: ignore[arg-type]
    return AsyncEvdcApiClient(client)


def test_async_delegates_to_sync_client(fake_session: FakeSession) -> None:
    fake_session.add("GET", "api/profile", FakeResponse(200, load_fixture("profile")))
    fake_session.add("GET", "api/hubject/ongoing-sessionsV2", FakeResponse(200, []))
    client = _async_client(fake_session)

    async def run() -> None:
        user = await client.get_profile()
        assert user.first_name == "Mario"
        assert await client.get_ongoing_sessions() == []
        await client.close()

    asyncio.run(run())
    assert fake_session.closed


def test_async_get_all_charge_history(fake_session: FakeSession) -> None:
    fake_session.add(
        "GET",
        "api/hubject/charge-history",
        FakeResponse(200, load_fixture("charge_history")),
        FakeResponse(200, load_fixture("charge_history_last")),
    )

    sessions = asyncio.run(_async_client(fake_session).get_all_charge_history(limit=2))

    assert len(sessions) == 3
