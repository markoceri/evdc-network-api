"""EVDC backend API client."""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import quote

import requests

from .const import (
    DEFAULT_APP_VERSION,
    DEFAULT_BASE_URL,
    DEFAULT_DEVICE_MODEL,
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT,
    PATH_CHARGE_HISTORY,
    PATH_EVSE,
    PATH_ONGOING_SESSIONS,
    PATH_PROFILE,
    PATH_RECEIPT,
    PATH_REFRESH_TOKEN,
    PATH_SIGN_IN,
    REQ_SCOPE,
)
from .crypto import encrypt_password
from .exceptions import EvdcApiError, EvdcAuthError, EvdcTwoFactorRequiredError
from .models import ChargingHistoryPage, ChargingSession, Evse, OngoingSession, Receipt, User

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import TracebackType

_LOGGER = logging.getLogger(__name__)


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
        """Log in with email and password and return the account."""
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
        access_token = data.get("accessToken")
        if not access_token:
            if data.get("isTwoFactorEnabled") or data.get("twoFactorMethod"):
                raise EvdcTwoFactorRequiredError("The account requires two-factor authentication.")
            raise EvdcAuthError("Login response has no access token.")
        self._set_tokens(str(access_token), _str(data.get("refreshToken")))
        user = User.from_dict(data)
        self.user_id = user.id
        _LOGGER.debug("EVDC login succeeded")
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


def _error_message(body: Any, status_code: int) -> str:
    message = body.get("message") if isinstance(body, dict) else None
    return f"{message} (HTTP {status_code})" if message else f"HTTP {status_code}"
