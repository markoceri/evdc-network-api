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
USER_SESSIONS = "api/user-sessions"
VERIFY_OTP = "api/verifyOTP"
RESEND_CODE = "api/resendVerificationCode"
TOTP_LOGIN = "api/2fa/totp/login"
TOTP_RECOVERY = "api/2fa/totp/recovery-login"


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


def test_login_with_2fa_raises_and_does_not_activate_session(fake_session: FakeSession) -> None:
    # The backend returns usable tokens even with 2FA on; the client must not use them before verification.
    fake_session.add(
        "POST",
        LOGIN,
        _ok({"data": {"isTwoFactorEnabled": True, "twoFactorMethod": "email", "accessToken": "pre-2fa-token"}}),
    )
    client = _client(fake_session)

    with pytest.raises(EvdcTwoFactorRequiredError) as excinfo:
        client.login()

    assert excinfo.value.method == "email"
    assert client.access_token is None
    assert client.logged_in is False
    assert client.two_factor_pending == "email"


def test_verify_two_factor_email_uses_response_tokens(fake_session: FakeSession) -> None:
    # verifyOTP returns the user and fresh tokens nested under "user" (verified shape).
    fake_session.add(
        "POST",
        LOGIN,
        _ok({"data": {"isTwoFactorEnabled": True, "twoFactorMethod": "email", "accessToken": "held-token"}}),
    )
    fake_session.add(
        "POST",
        VERIFY_OTP,
        _ok({"user": load_fixture("login")["data"], "message": "Verification code verified successfully."}),
    )
    client = _client(fake_session)
    with pytest.raises(EvdcTwoFactorRequiredError):
        client.login()

    user = client.verify_two_factor("2194")

    assert client.access_token == "test-access-token"
    assert client.refresh_token == "test-refresh-token"
    assert client.two_factor_pending is None
    assert user.email == "mario.rossi@example.com"
    assert fake_session.paths() == [LOGIN, VERIFY_OTP]  # no extra profile request
    otp_body = fake_session.calls[1].json
    assert otp_body == {"email": "mario.rossi@example.com", "otp": "2194", "isTwoFactorEnabled": True}


def test_verify_two_factor_email_falls_back_to_held_token(fake_session: FakeSession) -> None:
    # Defensive: if a verification response carries no tokens, use the ones held from the login step.
    fake_session.add(
        "POST",
        LOGIN,
        _ok(
            {
                "data": {
                    "isTwoFactorEnabled": True,
                    "twoFactorMethod": "email",
                    "accessToken": "held-token",
                    "refreshToken": "held-refresh",
                }
            }
        ),
    )
    fake_session.add("POST", VERIFY_OTP, _ok({"message": "verified"}))
    fake_session.add("GET", PROFILE, _ok(load_fixture("profile")))
    client = _client(fake_session)
    with pytest.raises(EvdcTwoFactorRequiredError):
        client.login()

    user = client.verify_two_factor("2194")

    assert client.access_token == "held-token"
    assert client.refresh_token == "held-refresh"
    assert user.email == "mario.rossi@example.com"


def test_verify_two_factor_totp_uses_held_token_and_root_user(fake_session: FakeSession) -> None:
    # signIn-enc holds a pre-2FA token; the TOTP endpoint needs it in Authorization and returns the user at the root.
    fake_session.add(
        "POST",
        LOGIN,
        _ok({"data": {"isTwoFactorEnabled": True, "twoFactorMethod": "totp", "accessToken": "pre-2fa"}}),
    )
    fake_session.add("POST", TOTP_LOGIN, _ok(load_fixture("login")["data"]))
    client = _client(fake_session)
    with pytest.raises(EvdcTwoFactorRequiredError):
        client.login()

    user = client.verify_two_factor("000111")

    assert client.access_token == "test-access-token"
    assert client.two_factor_pending is None
    assert user.email == "mario.rossi@example.com"
    assert fake_session.calls[1].path == TOTP_LOGIN
    assert fake_session.calls[1].headers["Authorization"] == "Bearer pre-2fa"
    assert fake_session.calls[1].json == {"email": "mario.rossi@example.com", "totpCode": "000111"}


def test_verify_recovery_code(fake_session: FakeSession) -> None:
    fake_session.add(
        "POST",
        LOGIN,
        _ok({"data": {"isTwoFactorEnabled": True, "twoFactorMethod": "totp", "accessToken": "pre-2fa"}}),
    )
    fake_session.add("POST", TOTP_RECOVERY, _ok(load_fixture("login")["data"]))
    client = _client(fake_session)
    with pytest.raises(EvdcTwoFactorRequiredError):
        client.login()

    client.verify_recovery_code("abcd-efgh")

    assert client.access_token == "test-access-token"
    assert fake_session.calls[1].path == TOTP_RECOVERY
    assert fake_session.calls[1].headers["Authorization"] == "Bearer pre-2fa"
    assert fake_session.calls[1].json == {"email": "mario.rossi@example.com", "recoveryCode": "abcd-efgh"}


def test_resend_two_factor_code(fake_session: FakeSession) -> None:
    fake_session.add("POST", LOGIN, _ok({"data": {"isTwoFactorEnabled": True, "twoFactorMethod": "email"}}))
    fake_session.add("POST", RESEND_CODE, _ok({"message": "sent"}))
    client = _client(fake_session)
    with pytest.raises(EvdcTwoFactorRequiredError):
        client.login()

    client.resend_two_factor_code()

    assert fake_session.calls[1].path == RESEND_CODE
    assert fake_session.calls[1].json == {"email": "mario.rossi@example.com", "isForgotPassword": False}


def test_verify_two_factor_without_pending_raises(fake_session: FakeSession) -> None:
    with pytest.raises(EvdcAuthError, match="pending"):
        _client(fake_session).verify_two_factor("123456")


# ---------------------------------------------------------------------------
# Biometric device-key login
# ---------------------------------------------------------------------------

BIOMETRIC_LOGIN = "api/biometric-login"
REMOVE_BIOMETRIC = "api/remove-biometricKey"


def test_enroll_device_key_registers_public_key(fake_session: FakeSession) -> None:
    from evdc_network_api.crypto import device_public_key

    fake_session.add("PUT", PROFILE, _ok({"message": "ok"}))
    client = _client(fake_session, access_token="token")
    client.user_id = "u1"  # already known, so enroll makes no extra profile request

    pem = client.enroll_device_key()

    assert "PRIVATE KEY" in pem
    assert fake_session.calls[0].method == "PUT"
    assert fake_session.calls[0].path == PROFILE
    assert fake_session.calls[0].json == {"biometricKey": device_public_key(pem)}


def test_login_with_device_key_signs_payload_and_sets_tokens(fake_session: FakeSession) -> None:
    import base64

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    from evdc_network_api.crypto import device_public_key, generate_device_key

    pem = generate_device_key()
    fake_session.add(
        "POST",
        BIOMETRIC_LOGIN,
        _ok({"accessToken": "bio-access", "refreshToken": "bio-refresh", "user": load_fixture("login")["data"]}),
    )
    client = _client(fake_session, password=None, device_key=pem, user_id="u1")

    user = client.login_with_device_key()

    assert client.access_token == "bio-access"
    assert client.refresh_token == "bio-refresh"
    assert user.email == "mario.rossi@example.com"
    body = fake_session.calls[0].json
    assert body is not None
    assert body["fcmToken"] and body["userId"] == "u1"
    # The signature must verify against the enrolled public key for the sent payload.
    public = serialization.load_der_public_key(base64.b64decode(device_public_key(pem)))
    assert isinstance(public, rsa.RSAPublicKey)
    public.verify(base64.b64decode(body["signature"]), body["payload"].encode(), padding.PKCS1v15(), hashes.SHA256())


def test_login_with_device_key_needs_key_and_user_id(fake_session: FakeSession) -> None:
    with pytest.raises(EvdcAuthError, match="device key"):
        _client(fake_session, password=None).login_with_device_key()
    with pytest.raises(EvdcAuthError, match="user_id"):
        _client(fake_session, password=None, device_key="x", user_id=None).login_with_device_key()


def test_device_key_is_preferred_over_password_login(fake_session: FakeSession) -> None:
    from evdc_network_api.crypto import generate_device_key

    fake_session.add("POST", BIOMETRIC_LOGIN, _ok({"accessToken": "bio", "user": load_fixture("login")["data"]}))
    fake_session.add("GET", ONGOING, _ok([]))
    client = _client(fake_session, device_key=generate_device_key(), user_id="u1")

    client.get_ongoing_sessions()  # auto-auth: should use the device key, not signIn-enc

    assert fake_session.paths() == [BIOMETRIC_LOGIN, ONGOING]


def test_remove_device_key(fake_session: FakeSession) -> None:
    from evdc_network_api.crypto import device_public_key, generate_device_key

    pem = generate_device_key()
    fake_session.add("POST", REMOVE_BIOMETRIC, _ok({"message": "removed"}))
    client = _client(fake_session, access_token="token", device_key=pem)

    client.remove_device_key()

    assert fake_session.calls[0].path == REMOVE_BIOMETRIC
    assert fake_session.calls[0].json == {"biometricKey": device_public_key(pem)}


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


def test_get_connected_sessions(fake_session: FakeSession) -> None:
    fake_session.add(
        "GET",
        USER_SESSIONS,
        _ok(
            {
                "data": [
                    {"_id": "s1", "deviceModel": "Pixel 8", "city": "Milano", "country": "IT", "isCurrent": True},
                    {"_id": "s2", "deviceModel": "iPhone", "city": "Roma", "country": "IT", "isCurrent": False},
                ]
            }
        ),
    )

    sessions = _client(fake_session, access_token="token").get_connected_sessions()

    assert [s.id for s in sessions] == ["s1", "s2"]
    assert sessions[0].is_current is True
    assert sessions[0].device_model == "Pixel 8"
    assert sessions[1].city == "Roma"


def test_revoke_session(fake_session: FakeSession) -> None:
    fake_session.add("DELETE", f"{USER_SESSIONS}/s2", FakeResponse(204, None))

    _client(fake_session, access_token="token").revoke_session("s2")

    assert fake_session.calls[0].method == "DELETE"
    assert fake_session.calls[0].path == f"{USER_SESSIONS}/s2"


def test_revoke_all_sessions(fake_session: FakeSession) -> None:
    fake_session.add("DELETE", USER_SESSIONS, _ok({"success": True}))

    _client(fake_session, access_token="token").revoke_all_sessions()

    assert fake_session.calls[0].method == "DELETE"
    assert fake_session.calls[0].path == USER_SESSIONS


WALLETS = "api/wallet/user/wallets"
WALLET_HISTORY = "api/wallet/history"
FAVOURITES = "api/favourite/stations"
NOTIFICATIONS = "api/notification/"


def test_get_favourite_stations(fake_session: FakeSession) -> None:
    fake_session.add("GET", FAVOURITES, _ok(load_fixture("favourite_stations")))

    stations = _client(fake_session, access_token="token").get_favourite_stations()

    assert len(stations) == 1
    evse = stations[0]
    assert evse.evse_id == "IT*TST*E0009*1"
    assert evse.status == "Available"
    assert evse.operator_name == "Test Charging Srl"
    assert evse.max_power_kw == 90
    assert evse.address is not None
    assert evse.address.city == "Torino"


def test_get_notifications(fake_session: FakeSession) -> None:
    fake_session.add("GET", NOTIFICATIONS, _ok(load_fixture("notifications")))

    page = _client(fake_session, access_token="token").get_notifications(page=1, limit=10)

    assert page.total == 2
    assert page.page == 1
    assert [n.type for n in page.notifications] == ["SESSION_PAID", "WALLET_TOPUP"]
    assert page.notifications[0].read is False
    assert page.notifications[0].title == "Charging complete"
    assert fake_session.calls[0].params == {"page": 1, "limit": 10, "success": "true"}


def test_count_unread_notifications(fake_session: FakeSession) -> None:
    fake_session.add("GET", NOTIFICATIONS, _ok(load_fixture("notifications")))

    assert _client(fake_session, access_token="token").count_unread_notifications() == 1
    assert fake_session.calls[0].params == {"page": 1, "limit": 50, "success": "true"}


def test_get_wallets(fake_session: FakeSession) -> None:
    fake_session.add("GET", WALLETS, _ok(load_fixture("wallets")))

    wallets = _client(fake_session, access_token="token").get_wallets()

    assert [w.currency for w in wallets] == ["EUR", "EVDC Token"]
    assert wallets[0].balance == pytest.approx(41.97)
    assert wallets[0].is_primary is True
    assert wallets[0].currency_symbol == "€"
    assert wallets[1].is_token is True
    assert wallets[1].balance == pytest.approx(352160.89)


def test_get_wallet_transactions(fake_session: FakeSession) -> None:
    fake_session.add("GET", WALLET_HISTORY, _ok(load_fixture("wallet_history")))

    page = _client(fake_session, access_token="token").get_wallet_transactions(page=1, limit=10)

    assert page.total == 2
    assert page.closing_balances["EUR"] == pytest.approx(41.97)
    first = page.transactions[0]
    assert first.amount == pytest.approx(-6.05)
    assert first.session_id == "00000000-0000-4000-8000-000000000001"
    assert first.category == "CHARGING"
    assert page.transactions[1].amount == pytest.approx(50.0)
    assert fake_session.calls[0].params == {"page": 1, "limit": 10}


def test_get_wallet_transactions_filters(fake_session: FakeSession) -> None:
    fake_session.add("GET", WALLET_HISTORY, _ok(load_fixture("wallet_history")))

    _client(fake_session, access_token="token").get_wallet_transactions(currency="EUR", is_token=False)

    assert fake_session.calls[0].params == {"page": 1, "limit": 10, "currency": "EUR", "isToken": "false"}


def test_iter_wallet_transactions_stops_at_last_page(fake_session: FakeSession) -> None:
    fake_session.add("GET", WALLET_HISTORY, _ok(load_fixture("wallet_history")))

    txns = list(_client(fake_session, access_token="token").iter_wallet_transactions(limit=10))

    assert len(txns) == 2
    assert len(fake_session.calls) == 1


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


# ---------------------------------------------------------------------------
# Nearby stations
# ---------------------------------------------------------------------------

NEARBY = "api/hubject/nearby/9.190000/45.464200"


def test_get_nearby_stations_puts_longitude_first(fake_session: FakeSession) -> None:
    fake_session.add("GET", NEARBY, _ok(load_fixture("nearby_page1")))

    stations = _client(fake_session, access_token="token").get_nearby_stations(45.4642, 9.19)

    assert fake_session.calls[0].path == NEARBY
    assert fake_session.calls[0].params == {"page": 1, "pageSize": 10}
    assert len(stations) == 10
    assert stations[0].distance_m == 150
    assert stations[0].pricing is not None
    assert stations[0].pricing.price == pytest.approx(0.45)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"latitude": 91.0, "longitude": 9.0}, "latitude"),
        ({"latitude": 45.0, "longitude": -181.0}, "longitude"),
        ({"latitude": 45.0, "longitude": 9.0, "page": 0}, "page"),
        ({"latitude": 45.0, "longitude": 9.0, "page_size": 101}, "page_size"),
    ],
)
def test_get_nearby_stations_validates_arguments(
    fake_session: FakeSession, kwargs: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _client(fake_session, access_token="token").get_nearby_stations(**kwargs)  # type: ignore[arg-type]
    assert fake_session.calls == []


@pytest.fixture
def small_search_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fixtures hold 10 items per page: make the radius search read pages of 10."""
    monkeypatch.setattr("evdc_network_api.client.NEARBY_SEARCH_PAGE_SIZE", 10)


def test_find_stations_near_reads_large_pages(fake_session: FakeSession) -> None:
    fake_session.add("GET", NEARBY, _ok(load_fixture("nearby_page1")))

    _client(fake_session, access_token="token").find_stations_near(45.4642, 9.19)

    assert [c.params for c in fake_session.calls] == [{"page": 1, "pageSize": 50}]


@pytest.mark.usefixtures("small_search_pages")
def test_find_stations_near_stops_at_radius(fake_session: FakeSession) -> None:
    fake_session.add("GET", NEARBY, _ok(load_fixture("nearby_page1")), _ok(load_fixture("nearby_page2")))

    stations = _client(fake_session, access_token="token").find_stations_near(45.4642, 9.19, radius_m=2000)

    # page 1: 150..1500 m; page 2 repeats the last item of page 1, then 1600, 1900, 2200 m
    assert [s.distance_m for s in stations] == [150.0 * n for n in range(1, 11)] + [1600.0, 1900.0]
    assert len({s.evse_id for s in stations}) == len(stations)
    assert [c.params for c in fake_session.calls] == [{"page": 1, "pageSize": 10}, {"page": 2, "pageSize": 10}]


@pytest.mark.usefixtures("small_search_pages")
def test_find_stations_near_small_radius_needs_one_request(fake_session: FakeSession) -> None:
    fake_session.add("GET", NEARBY, _ok(load_fixture("nearby_page1")))

    stations = _client(fake_session, access_token="token").find_stations_near(45.4642, 9.19, radius_m=500)

    assert [s.distance_m for s in stations] == [150.0, 300.0, 450.0]
    assert len(fake_session.calls) == 1


@pytest.mark.usefixtures("small_search_pages")
def test_find_stations_near_respects_max_results(fake_session: FakeSession) -> None:
    fake_session.add("GET", NEARBY, _ok(load_fixture("nearby_page1")))

    stations = _client(fake_session, access_token="token").find_stations_near(
        45.4642, 9.19, radius_m=100_000, max_results=4
    )

    assert len(stations) == 4
    assert len(fake_session.calls) == 1


@pytest.mark.usefixtures("small_search_pages")
def test_find_stations_near_stops_on_short_page(fake_session: FakeSession) -> None:
    fake_session.add("GET", NEARBY, _ok({"result": load_fixture("nearby_page1")["result"][:3]}))

    stations = _client(fake_session, access_token="token").find_stations_near(45.4642, 9.19, radius_m=100_000)

    assert len(stations) == 3
    assert len(fake_session.calls) == 1


@pytest.mark.usefixtures("small_search_pages")
def test_find_stations_near_has_no_default_result_limit(fake_session: FakeSession) -> None:
    pages = [
        _ok({"result": [{"EvseID": f"IT*FAK*E{n:03d}", "distance": float(n)} for n in range(p * 10, p * 10 + 10)]})
        for p in range(15)
    ]
    fake_session.add("GET", NEARBY, *pages, _ok({"result": []}))

    stations = _client(fake_session, access_token="token").find_stations_near(45.4642, 9.19, radius_m=100_000)

    assert len(stations) == 150
    assert len(fake_session.calls) == 16


@pytest.mark.usefixtures("small_search_pages")
def test_find_stations_near_stops_when_pages_repeat(fake_session: FakeSession) -> None:
    # a backend ignoring ``page`` would return the same page forever
    fake_session.add("GET", NEARBY, _ok(load_fixture("nearby_page1")))

    stations = _client(fake_session, access_token="token").find_stations_near(45.4642, 9.19, radius_m=100_000)

    assert len(stations) == 10
    assert len(fake_session.calls) == 2


@pytest.mark.parametrize(("kwargs", "message"), [({"radius_m": 0}, "radius_m"), ({"max_results": 0}, "max_results")])
def test_find_stations_near_validates_arguments(
    fake_session: FakeSession, kwargs: dict[str, float], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _client(fake_session, access_token="token").find_stations_near(45.0, 9.0, **kwargs)  # type: ignore[arg-type]
    assert fake_session.calls == []
