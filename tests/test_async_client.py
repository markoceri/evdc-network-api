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


def test_async_find_stations_near(fake_session: FakeSession) -> None:
    fake_session.add("GET", "api/hubject/nearby/9.000000/45.000000", FakeResponse(200, load_fixture("nearby_page1")))

    stations = asyncio.run(_async_client(fake_session).find_stations_near(45.0, 9.0, radius_m=400))

    assert [s.distance_m for s in stations] == [150.0, 300.0]


def test_async_device_key_login(fake_session: FakeSession) -> None:
    from evdc_network_api.client import EvdcApiClient
    from evdc_network_api.crypto import generate_device_key

    fake_session.add("POST", "api/biometric-login", FakeResponse(200, {"accessToken": "bio", "user": {"_id": "u1"}}))
    sync = EvdcApiClient(email="x@example.com", device_key=generate_device_key(), user_id="u1", session=fake_session)  # type: ignore[arg-type]
    client = AsyncEvdcApiClient(sync)

    user = asyncio.run(client.login_with_device_key())

    assert sync.access_token == "bio"
    assert user.id == "u1"


def test_async_connected_sessions(fake_session: FakeSession) -> None:
    fake_session.add("GET", "api/user-sessions", FakeResponse(200, {"data": [{"_id": "s1", "isCurrent": True}]}))
    fake_session.add("DELETE", "api/user-sessions/s1", FakeResponse(204, None))
    fake_session.add("DELETE", "api/user-sessions", FakeResponse(200, {"success": True}))
    client = _async_client(fake_session)

    async def run() -> None:
        sessions = await client.get_connected_sessions()
        assert [s.id for s in sessions] == ["s1"]
        await client.revoke_session("s1")
        await client.revoke_all_sessions()

    asyncio.run(run())
    assert [c.method for c in fake_session.calls] == ["GET", "DELETE", "DELETE"]
