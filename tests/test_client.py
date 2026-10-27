"""Tests for evdc_network_api.client."""

from __future__ import annotations

import base64
import logging

import pytest

from evdc_network_api.client import EvdcApiClient
from evdc_network_api.exceptions import EvdcApiError, EvdcAuthError, EvdcTwoFactorRequiredError

from .conftest import FakeResponse, FakeSession, load_fixture

LOGIN = "api/signIn-enc"
REFRESH = "api/refresh-token"
PROFILE = "api/profile"
HISTORY = "api/hubject/charge-history"
ONGOING = "api/hubject/ongoing-sessionsV2"


def _client(session: FakeSession, **kwargs: object) -> EvdcApiClient:
    params: dict[str, object] = {"email": "mario.rossi@example.com", "password": "hunter2", "session": session}
    params.update(kwargs)
    return EvdcApiClient(**params)  # type: ignore[arg-type]


def _ok(body: object) -> FakeResponse:
    return FakeResponse(200, body)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def test_login_sets_tokens_and_returns_user(fake_session: FakeSession) -> None:
    fake_session.add("POST", LOGIN, _ok(load_fixture("login")))
    client = _client(fake_session)

    user = client.login()

    assert user.email == "mario.rossi@example.com"
    assert client.access_token == "test-access-token"
    assert client.refresh_token == "test-refresh-token"
    assert client.user_id == "64b7f0c2a1b2c3d4e5f60718"
    body = fake_session.calls[0].json
    assert body is not None
    assert body["email"] == "mario.rossi@example.com"
    assert body["password"] != "hunter2"
    assert len(base64.b64decode(body["password"])) == 256
    assert "Authorization" not in fake_session.calls[0].headers


def test_requests_carry_app_headers(fake_session: FakeSession) -> None:
    fake_session.add("POST", LOGIN, _ok(load_fixture("login")))
    fake_session.add("GET", PROFILE, _ok(load_fixture("profile")))
    client = _client(fake_session, device_id="a" * 64)

    client.get_profile()

    headers = fake_session.calls[1].headers
    assert headers["Authorization"] == "Bearer test-access-token"
    assert headers["req-scope"] == "MOBILEMED-FE"
    assert headers["x-device-id"] == "a" * 64
    assert headers["x-user-id"] == "64b7f0c2a1b2c3d4e5f60718"
    assert headers["x-app-version"]
    assert headers["x-device-model"]
    assert headers["x-request-id"] != fake_session.calls[0].headers["x-request-id"]


def test_default_device_id_is_64_hex() -> None:
    client = EvdcApiClient(email="x@example.com", password="p", session=FakeSession())  # type: ignore[arg-type]
    assert len(client.device_id) == 64
    int(client.device_id, 16)


def test_login_error_raises_auth_error_with_server_message(fake_session: FakeSession) -> None:
    fake_session.add(
        "POST",
        LOGIN,
        FakeResponse(400, {"message": "User is already register with social platform", "errors": []}),
    )
    with pytest.raises(EvdcAuthError, match="social platform") as excinfo:
        _client(fake_session).login()
    assert excinfo.value.status_code == 400


def test_login_without_token_and_2fa_raises_two_factor_error(fake_session: FakeSession) -> None:
    fake_session.add("POST", LOGIN, _ok({"data": {"isTwoFactorEnabled": True, "twoFactorMethod": "email"}}))
    with pytest.raises(EvdcTwoFactorRequiredError):
        _client(fake_session).login()


def test_login_needs_password(fake_session: FakeSession) -> None:
    with pytest.raises(EvdcAuthError, match="password"):
        _client(fake_session, password=None).login()


def test_first_call_logs_in_automatically(fake_session: FakeSession) -> None:
    fake_session.add("POST", LOGIN, _ok(load_fixture("login")))
    fake_session.add("GET", ONGOING, _ok([]))

    assert _client(fake_session).get_ongoing_sessions() == []
    assert fake_session.paths() == [LOGIN, ONGOING]


def test_stored_refresh_token_is_used_instead_of_login(fake_session: FakeSession) -> None:
    fake_session.add("POST", REFRESH, _ok({"accessToken": "fresh-token"}))
    fake_session.add("GET", ONGOING, _ok([]))
    client = _client(fake_session, password=None, refresh_token="stored-refresh")

    client.get_ongoing_sessions()

    assert fake_session.paths() == [REFRESH, ONGOING]
    assert fake_session.calls[0].json == {"refreshToken": "stored-refresh"}
    assert fake_session.calls[1].headers["Authorization"] == "Bearer fresh-token"
    assert client.refresh_token == "stored-refresh"


def test_401_triggers_refresh_and_retry(fake_session: FakeSession) -> None:
    fake_session.add("GET", ONGOING, FakeResponse(401, {"message": "jwt expired"}), _ok([]))
    fake_session.add("POST", REFRESH, _ok({"data": {"accessToken": "new-token", "refreshToken": "new-refresh"}}))
    updates: list[tuple[str, str | None]] = []
    client = _client(
        fake_session,
        access_token="old-token",
        refresh_token="old-refresh",
        on_tokens_updated=lambda a, r: updates.append((a, r)),
    )

    client.get_ongoing_sessions()

    assert fake_session.paths() == [ONGOING, REFRESH, ONGOING]
    assert fake_session.calls[2].headers["Authorization"] == "Bearer new-token"
    assert updates == [("new-token", "new-refresh")]


def test_failed_refresh_falls_back_to_login(fake_session: FakeSession) -> None:
    fake_session.add("GET", ONGOING, FakeResponse(401, {"message": "jwt expired"}), _ok([]))
    fake_session.add("POST", REFRESH, FakeResponse(401, {"message": "invalid refresh token"}))
    fake_session.add("POST", LOGIN, _ok(load_fixture("login")))
    client = _client(fake_session, access_token="old-token", refresh_token="old-refresh")

    client.get_ongoing_sessions()

    assert fake_session.paths() == [ONGOING, REFRESH, LOGIN, ONGOING]
    assert client.access_token == "test-access-token"


def test_failed_refresh_without_password_raises(fake_session: FakeSession) -> None:
    fake_session.add("GET", ONGOING, FakeResponse(401, {"message": "jwt expired"}))
    fake_session.add("POST", REFRESH, FakeResponse(401, {"message": "invalid refresh token"}))
    client = _client(fake_session, password=None, access_token="old", refresh_token="old")

    with pytest.raises(EvdcAuthError):
        client.get_ongoing_sessions()


def test_non_auth_errors_are_not_retried(fake_session: FakeSession) -> None:
    fake_session.add("GET", ONGOING, FakeResponse(500, {"message": "boom"}))
    client = _client(fake_session, access_token="token")

    with pytest.raises(EvdcApiError, match="boom") as excinfo:
        client.get_ongoing_sessions()
    assert excinfo.value.status_code == 500
    assert fake_session.paths() == [ONGOING]


def test_network_error_is_wrapped(fake_session: FakeSession) -> None:
    with pytest.raises(EvdcApiError, match="HTTP request failed"):
        _client(fake_session, access_token="token").get_profile()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def test_get_profile(fake_session: FakeSession) -> None:
    fake_session.add("GET", PROFILE, _ok(load_fixture("profile")))
    client = _client(fake_session, access_token="token")

    user = client.get_profile()

    assert user.last_name == "Rossi"
    assert client.user_id == user.id


def test_get_charge_history_sends_pagination(fake_session: FakeSession) -> None:
    fake_session.add("GET", HISTORY, _ok(load_fixture("charge_history")))

    page = _client(fake_session, access_token="token").get_charge_history(page=1, limit=2)

    assert fake_session.calls[0].params == {"page": 1, "limit": 2}
    assert [s.invoice_no for s in page.sessions] == ["INV-TEST-0001", "INV-TEST-0002"]


def test_iter_charge_history_walks_all_pages(fake_session: FakeSession) -> None:
    fake_session.add("GET", HISTORY, _ok(load_fixture("charge_history")), _ok(load_fixture("charge_history_last")))

    sessions = list(_client(fake_session, access_token="token").iter_charge_history(limit=2))

    assert [s.invoice_no for s in sessions] == ["INV-TEST-0001", "INV-TEST-0002", "INV-TEST-0003"]
    assert [c.params for c in fake_session.calls] == [{"page": 1, "limit": 2}, {"page": 2, "limit": 2}]


def test_iter_charge_history_respects_max_pages(fake_session: FakeSession) -> None:
    fake_session.add("GET", HISTORY, _ok(load_fixture("charge_history")))

    sessions = list(_client(fake_session, access_token="token").iter_charge_history(limit=2, max_pages=1))

    assert len(sessions) == 2
    assert len(fake_session.calls) == 1


def test_iter_charge_history_empty(fake_session: FakeSession) -> None:
    fake_session.add("GET", HISTORY, _ok({"page": 1, "limit": 10, "totalPages": 0, "totalDocuments": 0, "data": []}))

    assert list(_client(fake_session, access_token="token").iter_charge_history()) == []


@pytest.mark.parametrize(
    "body",
    [
        load_fixture("ongoing_sessions"),
        {"data": load_fixture("ongoing_sessions")},
        {"result": load_fixture("ongoing_sessions")},
        {"result": {"data": load_fixture("ongoing_sessions")}},
    ],
)
def test_get_ongoing_sessions_envelopes(fake_session: FakeSession, body: object) -> None:
    fake_session.add("GET", ONGOING, _ok(body))

    sessions = _client(fake_session, access_token="token").get_ongoing_sessions()

    assert [s.evse_id for s in sessions] == ["IT*TST*E0001*1"]


def test_get_receipt(fake_session: FakeSession) -> None:
    session_id = "00000000-0000-4000-8000-000000000001"
    fake_session.add("GET", f"api/hubject/download-pdf/{session_id}", _ok(load_fixture("receipt")))

    receipt = _client(fake_session, access_token="token").get_receipt(session_id)

    assert receipt.content.startswith(b"%PDF-")


def test_get_receipt_under_data_envelope(fake_session: FakeSession) -> None:
    fake_session.add("GET", "api/hubject/download-pdf/s1", _ok({"data": load_fixture("receipt")}))

    assert _client(fake_session, access_token="token").get_receipt("s1").content.startswith(b"%PDF-")


def test_get_receipt_without_content(fake_session: FakeSession) -> None:
    fake_session.add("GET", "api/hubject/download-pdf/s1", _ok({"message": "not found"}))

    with pytest.raises(EvdcApiError, match="base64"):
        _client(fake_session, access_token="token").get_receipt("s1")


def test_get_evse_keeps_asterisks_in_path(fake_session: FakeSession) -> None:
    fake_session.add("GET", "api/hubject/IT*TST*E0001*1", _ok({"result": load_fixture("evse")}))

    evse = _client(fake_session, access_token="token").get_evse("IT*TST*E0001*1")

    assert evse.operator_name == "Test Charging Srl"


# ---------------------------------------------------------------------------
# Secrets hygiene
# ---------------------------------------------------------------------------


def test_repr_hides_secrets(fake_session: FakeSession) -> None:
    client = _client(fake_session, access_token="secret-access", refresh_token="secret-refresh")
    text = repr(client)
    assert "hunter2" not in text
    assert "secret-access" not in text
    assert "secret-refresh" not in text
    assert "logged_in=True" in text


def test_logs_do_not_contain_secrets(fake_session: FakeSession, caplog: pytest.LogCaptureFixture) -> None:
    fake_session.add("POST", LOGIN, _ok(load_fixture("login")))
    fake_session.add("GET", PROFILE, _ok(load_fixture("profile")))
    caplog.set_level(logging.DEBUG, logger="evdc_network_api")

    _client(fake_session).get_profile()

    for secret in ("hunter2", "test-access-token", "test-refresh-token", "mario.rossi@example.com"):
        assert secret not in caplog.text


def test_context_manager_closes_session(fake_session: FakeSession) -> None:
    with _client(fake_session):
        pass
    assert fake_session.closed
