"""EVDC backend API client."""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import quote

import requests

from .const import (
    DEFAULT_APP_VERSION,
    DEFAULT_BASE_URL,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_NEARBY_RADIUS_M,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    MAX_NEARBY_PAGE_SIZE,
    NEARBY_PAGE_SIZE,
    NEARBY_SEARCH_PAGE_SIZE,
    PATH_CHARGE_HISTORY,
    PATH_EVSE,
    PATH_NEARBY,
    PATH_ONGOING_SESSIONS,
    PATH_PROFILE,
    PATH_RECEIPT,
    PATH_REFRESH_TOKEN,
    PATH_RESEND_CODE,
    PATH_SIGN_IN,
    PATH_TOTP_LOGIN,
    PATH_TOTP_RECOVERY_LOGIN,
    PATH_VERIFY_OTP,
    REQ_SCOPE,
    TWO_FACTOR_METHOD_EMAIL,
    TWO_FACTOR_METHOD_TOTP,
)
from .crypto import encrypt_password
from .exceptions import EvdcApiError, EvdcAuthError, EvdcTwoFactorRequiredError
from .models import ChargingHistoryPage, ChargingSession, Evse, OngoingSession, Receipt, User

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import TracebackType

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _PendingTwoFactor:
    """A login waiting for a verification code.

    ``method`` is ``"email"`` or ``"totp"``. Any tokens returned by the login step are held here and only promoted
    to the active session once the verification code is accepted, so the library never uses a session while
    two-factor verification is still pending.
    """

    method: str
    access_token: str | None
    refresh_token: str | None


class EvdcApiClient:
    """Client for the EVDC charging network backend.

    Reads the authenticated user's own data: profile, charging history, receipts, ongoing sessions and the stations
    they ran on. Authentication is automatic: the first call logs in, an expired access token is refreshed with the
    refresh token, and a failed refresh falls back to a full login.

    To avoid a login on every start, persist the tokens (``on_tokens_updated``) and pass them back as
    ``access_token`` / ``refresh_token``.
    """

    def __init__(
        self,
        *,
        email: str,
        password: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        device_id: str | None = None,
        device_model: str = DEFAULT_DEVICE_MODEL,
        app_version: str = DEFAULT_APP_VERSION,
        session: requests.Session | None = None,
        on_tokens_updated: Callable[[str, str | None], None] | None = None,
    ) -> None:
        self.email = email
        self._password = password
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        # The app sends a stable 64-hex device id (HMAC-SHA256 of the Android ID). Pass the same value across runs.
        self.device_id = device_id or secrets.token_hex(32)
        self.device_model = device_model
        self.app_version = app_version
        self.session = session or requests.Session()
        self.on_tokens_updated = on_tokens_updated
        self.user_id: str | None = None
        self._pending_two_factor: _PendingTwoFactor | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(email={self.email!r}, base_url={self.base_url!r}, logged_in={self.logged_in})"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def logged_in(self) -> bool:
        return self.access_token is not None

    def close(self) -> None:
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def login(self) -> User:
        """Log in with email and password and return the account.

        When the account has two-factor authentication enabled, this raises :class:`EvdcTwoFactorRequiredError`
        without activating the session; complete it with :meth:`verify_two_factor`.
        """
        if not self._password:
            raise EvdcAuthError("A password is required to log in.")
        body = self._request(
            "POST",
            PATH_SIGN_IN,
            json={"email": self.email, "password": encrypt_password(self._password)},
            auth=False,
            error_cls=EvdcAuthError,
        )
        data = _dict(body.get("data")) or _dict(body)
        # Respect the second factor: hold any tokens the login returns and activate the session only after the
        # verification code is accepted (see verify_two_factor).
        if data.get("isTwoFactorEnabled") or data.get("twoFactorMethod"):
            method = _str(data.get("twoFactorMethod")) or TWO_FACTOR_METHOD_EMAIL
            self.access_token = None
            self._pending_two_factor = _PendingTwoFactor(
                method=method,
                access_token=_str(data.get("accessToken")),
                refresh_token=_str(data.get("refreshToken")),
            )
            _LOGGER.debug("EVDC login needs a two-factor code (method=%s)", method)
            raise EvdcTwoFactorRequiredError(f"The account requires two-factor verification ({method}).", method=method)
        access_token = data.get("accessToken")
        if not access_token:
            raise EvdcAuthError("Login response has no access token.")
        self._pending_two_factor = None
        self._set_tokens(str(access_token), _str(data.get("refreshToken")))
        user = User.from_dict(data)
        self.user_id = user.id
        _LOGGER.debug("EVDC login succeeded")
        return user

    @property
    def two_factor_pending(self) -> str | None:
        """The pending second factor (``"email"`` / ``"totp"``), or ``None`` if none is awaiting a code."""
        return self._pending_two_factor.method if self._pending_two_factor else None

    def verify_two_factor(self, code: str) -> User:
        """Complete a login pending two-factor verification with the code the backend asked for.

        Use the e-mail one-time code for the ``"email"`` factor, or the authenticator code for ``"totp"``.
        """
        pending = self._require_pending_two_factor()
        if pending.method == TWO_FACTOR_METHOD_TOTP:
            body = self._request(
                "POST",
                PATH_TOTP_LOGIN,
                json={"email": self.email, "totpCode": code},
                auth=False,
                error_cls=EvdcAuthError,
            )
        else:
            body = self._request(
                "POST",
                PATH_VERIFY_OTP,
                json={"email": self.email, "otp": code, "isTwoFactorEnabled": True},
                auth=False,
                error_cls=EvdcAuthError,
            )
        return self._complete_two_factor(body, pending)

    def verify_recovery_code(self, code: str) -> User:
        """Complete a pending TOTP login with a recovery code instead of the authenticator code."""
        pending = self._require_pending_two_factor()
        body = self._request(
            "POST",
            PATH_TOTP_RECOVERY_LOGIN,
            json={"email": self.email, "recoveryCode": code},
            auth=False,
            error_cls=EvdcAuthError,
        )
        return self._complete_two_factor(body, pending)

    def resend_two_factor_code(self) -> None:
        """Ask the backend to send the e-mail verification code again."""
        self._require_pending_two_factor()
        self._request(
            "POST",
            PATH_RESEND_CODE,
            json={"email": self.email, "isForgotPassword": False},
            auth=False,
            error_cls=EvdcAuthError,
        )

    def _require_pending_two_factor(self) -> _PendingTwoFactor:
        if self._pending_two_factor is None:
            raise EvdcAuthError("No two-factor verification is pending; log in first.")
        return self._pending_two_factor

    def _complete_two_factor(self, body: dict[str, Any], pending: _PendingTwoFactor) -> User:
        """Activate the session once a verification succeeds, from the response tokens or the held ones.

        The verification responses carry the user and fresh tokens under different keys: ``verifyOTP`` nests them in
        ``user``, the TOTP endpoints in ``data``. Fall back to the tokens held from the login step if neither is set.
        """
        data = _dict(body.get("data")) or _dict(body.get("user")) or _dict(body)
        access_token = _str(data.get("accessToken")) or pending.access_token
        if not access_token:
            raise EvdcAuthError("Two-factor verification returned no access token.")
        self._pending_two_factor = None
        self._set_tokens(access_token, _str(data.get("refreshToken")) or pending.refresh_token)
        user = User.from_dict(data) if data.get("email") else self.get_profile()
        self.user_id = user.id or self.user_id
        _LOGGER.debug("EVDC two-factor verification succeeded")
        return user

    def token_refresh(self) -> None:
        """Get a new access token from the refresh token."""
        if not self.refresh_token:
            raise EvdcAuthError("No refresh token available; a full login is required.")
        body = self._request(
            "POST",
            PATH_REFRESH_TOKEN,
            json={"refreshToken": self.refresh_token},
            auth=False,
            error_cls=EvdcAuthError,
        )
        data = body if body.get("accessToken") else _dict(body.get("data"))
        access_token = data.get("accessToken")
        if not access_token:
            raise EvdcAuthError("Refresh response has no access token.")
        self._set_tokens(str(access_token), _str(data.get("refreshToken")) or self.refresh_token)
        _LOGGER.debug("EVDC access token refreshed")

    def _set_tokens(self, access_token: str, refresh_token: str | None) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        if self.on_tokens_updated is not None:
            self.on_tokens_updated(access_token, refresh_token)

    def _ensure_token(self) -> None:
        if self.access_token:
            return
        if self.refresh_token:
            try:
                self.token_refresh()
                return
            except EvdcAuthError:
                _LOGGER.debug("Token refresh failed, falling back to full login")
        self.login()

    def _reauthenticate(self) -> None:
        """Called after a 401: refresh once, or log in again if the refresh fails."""
        self.access_token = None
        try:
            self.token_refresh()
        except EvdcAuthError:
            if not self._password:
                raise
            _LOGGER.debug("Token refresh failed, falling back to full login")
            self.login()

    # ------------------------------------------------------------------
    # Public API — data
    # ------------------------------------------------------------------

    def get_profile(self) -> User:
        """Fetch the account profile."""
        user = User.from_dict(_dict(self._authed("GET", PATH_PROFILE)))
        self.user_id = user.id or self.user_id
        return user

    def get_charge_history(self, page: int = 1, limit: int = DEFAULT_PAGE_SIZE) -> ChargingHistoryPage:
        """Fetch one page of completed charging sessions (1-based *page*)."""
        body = self._authed("GET", PATH_CHARGE_HISTORY, params={"page": page, "limit": limit})
        return ChargingHistoryPage.from_dict(_dict(body))

    def iter_charge_history(
        self, limit: int = DEFAULT_PAGE_SIZE, max_pages: int | None = None
    ) -> Iterator[ChargingSession]:
        """Iterate over the whole charging history, newest first, one page request at a time."""
        page = 1
        while max_pages is None or page <= max_pages:
            result = self.get_charge_history(page=page, limit=limit)
            yield from result.sessions
            if not result.sessions or not result.has_next:
                return
            page += 1

    def get_ongoing_sessions(self) -> list[OngoingSession]:
        """Fetch the sessions currently in progress (empty list when not charging)."""
        body = self._authed("GET", PATH_ONGOING_SESSIONS)
        return [OngoingSession.from_dict(item) for item in _items(body)]

    def get_receipt(self, session_id: str) -> Receipt:
        """Download the PDF receipt of a completed session."""
        body = _dict(self._authed("GET", PATH_RECEIPT.format(session_id=quote(session_id, safe=""))))
        payload = body if "base64" in body else _dict(body.get("data"))
        try:
            return Receipt.from_dict(payload)
        except ValueError as exc:
            raise EvdcApiError(str(exc)) from exc

    def get_evse(self, evse_id: str) -> Evse:
        """Fetch a charging point by its EVSE id (e.g. ``IT*ABC*E123*1``)."""
        body = self._authed("GET", PATH_EVSE.format(evse_id=quote(evse_id, safe="*")))
        payload = _dict(body)
        for key in ("result", "data"):
            if isinstance(payload.get(key), dict):
                payload = payload[key]
                break
        return Evse.from_dict(payload)

    def get_nearby_stations(
        self, latitude: float, longitude: float, page: int = 1, page_size: int = NEARBY_PAGE_SIZE
    ) -> list[Evse]:
        """Fetch one page of charging points around a point, nearest first, with their price and live status.

        Each item is one connector (EVSE); a station with two sockets appears twice. ``distance_m`` is the
        distance from the point. The backend has no radius: use :meth:`find_stations_near` to stop at one.
        """
        _check_coordinates(latitude, longitude)
        if page < 1:
            raise ValueError("page must be >= 1")
        if not 1 <= page_size <= MAX_NEARBY_PAGE_SIZE:
            raise ValueError(f"page_size must be between 1 and {MAX_NEARBY_PAGE_SIZE}")
        path = PATH_NEARBY.format(longitude=_coordinate(longitude), latitude=_coordinate(latitude))
        body = self._authed("GET", path, params={"page": page, "pageSize": page_size})
        return [Evse.from_dict(item) for item in _items(body)]

    def find_stations_near(
        self,
        latitude: float,
        longitude: float,
        *,
        radius_m: float = DEFAULT_NEARBY_RADIUS_M,
        max_results: int | None = None,
    ) -> list[Evse]:
        """Charging points within *radius_m* metres of a point (e.g. the vehicle), nearest first.

        The backend has no radius parameter: pages are read nearest first and the walk stops at the first result
        farther than *radius_m*, at the last page, or after *max_results* results when given. The radius is what
        bounds the number of requests, so keep it to the area around one location rather than sweeping a region.
        """
        if radius_m <= 0:
            raise ValueError("radius_m must be positive")
        if max_results is not None and max_results < 1:
            raise ValueError("max_results must be >= 1")
        results: list[Evse] = []
        seen: set[str] = set()
        page = 1
        while True:
            batch = self.get_nearby_stations(latitude, longitude, page=page, page_size=NEARBY_SEARCH_PAGE_SIZE)
            added = 0
            for evse in batch:
                if evse.distance_m is not None and evse.distance_m > radius_m:
                    return results
                key = evse.evse_id or evse.id
                if key is not None and key in seen:
                    continue
                if key is not None:
                    seen.add(key)
                results.append(evse)
                added += 1
                if max_results is not None and len(results) >= max_results:
                    return results
            # A short page is the last one; a page with nothing new means the backend is not paging further.
            if len(batch) < NEARBY_SEARCH_PAGE_SIZE or not added:
                return results
            page += 1

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _authed(self, method: str, path: str, **kwargs: Any) -> Any:
        """Authenticated request, retried once after re-authentication on HTTP 401."""
        self._ensure_token()
        try:
            return self._request(method, path, **kwargs)
        except EvdcAuthError as exc:
            if exc.status_code != 401:
                raise
            _LOGGER.debug("Access token rejected, re-authenticating")
            self._reauthenticate()
            return self._request(method, path, **kwargs)

    def _headers(self, *, auth: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "req-scope": REQ_SCOPE,
            "x-device-id": self.device_id,
            "x-device-model": self.device_model,
            "x-app-version": self.app_version,
            "x-request-id": str(uuid.uuid4()),
        }
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
            if self.user_id:
                headers["x-user-id"] = self.user_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        auth: bool = True,
        error_cls: type[EvdcApiError] = EvdcApiError,
    ) -> Any:
        url = self.base_url + path.lstrip("/")
        try:
            resp = self.session.request(
                method, url, headers=self._headers(auth=auth), params=params, json=json, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise EvdcApiError(f"HTTP request failed: {type(exc).__name__}") from exc

        _LOGGER.debug("EVDC %s %s -> HTTP %s", method, path, resp.status_code)
        try:
            body: Any = resp.json()
        except ValueError:
            body = None

        if resp.status_code == 401:
            raise EvdcAuthError(_error_message(body, resp.status_code), status_code=401)
        if not resp.ok:
            raise error_cls(_error_message(body, resp.status_code), status_code=resp.status_code)
        if body is None:
            raise EvdcApiError(f"Response is not JSON (HTTP {resp.status_code})", status_code=resp.status_code)
        return body


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str | None:
    return str(value) if value else None


def _items(body: Any) -> list[dict[str, Any]]:
    """Extract a list of objects from a bare array or a ``data`` / ``result`` envelope."""
    candidates = [body]
    if isinstance(body, dict):
        result = body.get("result")
        candidates += [body.get("data"), result, result.get("data") if isinstance(result, dict) else None]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


def _check_coordinates(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError(f"latitude out of range: {latitude}")
    if not -180 <= longitude <= 180:
        raise ValueError(f"longitude out of range: {longitude}")


def _coordinate(value: float) -> str:
    """Decimal degrees without scientific notation, 6 decimals (~0.1 m)."""
    return f"{value:.6f}"


def _error_message(body: Any, status_code: int) -> str:
    message = body.get("message") if isinstance(body, dict) else None
    return f"{message} (HTTP {status_code})" if message else f"HTTP {status_code}"
