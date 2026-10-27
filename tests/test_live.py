"""Tests for evdc_network_api.live (handlers only, no network)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from evdc_network_api.client import EvdcApiClient
from evdc_network_api.live import EvdcLiveClient

from .conftest import FakeResponse, FakeSession, load_fixture

if TYPE_CHECKING:
    from evdc_network_api.models import SessionProgress


def _live(session: FakeSession, received: list[SessionProgress]) -> tuple[EvdcLiveClient, EvdcApiClient]:
    client = EvdcApiClient(  # type: ignore[arg-type]
        email="x@example.com", access_token="old-token", refresh_token="refresh", session=session
    )
    return EvdcLiveClient(client, received.append), client


def test_progress_event_is_parsed_and_dispatched(fake_session: FakeSession) -> None:
    received: list[SessionProgress] = []
    live, _ = _live(fake_session, received)

    live._handle_progress(load_fixture("session_progress"))

    assert len(received) == 1
    assert received[0].evse_id == "IT*TST*E0001*1"


def test_progress_event_without_evse_id_is_ignored(fake_session: FakeSession) -> None:
    received: list[SessionProgress] = []
    live, _ = _live(fake_session, received)

    live._handle_progress({"Power": 11})
    live._handle_progress("not a dict")

    assert received == []


def test_url_carries_token(fake_session: FakeSession) -> None:
    live, _ = _live(fake_session, [])
    assert live._url() == "https://api-v2.evdccharge.co/?token=old-token"


def test_auth_error_refreshes_token_for_next_reconnect(fake_session: FakeSession) -> None:
    fake_session.add("POST", "api/refresh-token", FakeResponse(200, {"accessToken": "new-token"}))
    live, client = _live(fake_session, [])

    live._handle_connect_error({"message": "Authentication error"})

    assert client.access_token == "new-token"
    assert live._sio.connection_url == "https://api-v2.evdccharge.co/?token=new-token"


def test_other_connect_errors_do_not_refresh(fake_session: FakeSession) -> None:
    live, client = _live(fake_session, [])

    live._handle_connect_error("timeout")

    assert fake_session.calls == []
    assert client.access_token == "old-token"
