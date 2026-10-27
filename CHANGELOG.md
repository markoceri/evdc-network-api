# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `EvdcApiClient`, a synchronous client for the EVDC backend (`https://api-v2.evdccharge.co/`), and
  `AsyncEvdcApiClient`, an `asyncio.to_thread()` wrapper around it.
- Login with email and password through `/api/signIn-enc`. The password is encrypted with RSA-OAEP (SHA-256) using
  the app's public key, as the app does. The client sends the app's headers (`req-scope`, `x-device-id`,
  `x-device-model`, `x-app-version`, `x-request-id`) and a stable random device id.
- Automatic authentication: the first call logs in, an HTTP 401 triggers one refresh through `/api/refresh-token`
  and a failed refresh falls back to a full login. Tokens can be persisted with `on_tokens_updated` and passed back
  as `access_token` / `refresh_token`.
- `get_profile()` → `User`, verified against a real response.
- `get_charge_history(page, limit)` → `ChargingHistoryPage` with the backend's pagination counters, and
  `iter_charge_history()` over all pages. The page envelope is verified; the `ChargingSession` fields are
  reconstructed from the app and not yet seen populated.
- `get_ongoing_sessions()` → `list[OngoingSession]`, `get_receipt(session_id)` → `Receipt` (decoded PDF) and
  `get_evse(evse_id)` → `Evse`, all reconstructed from the app.
- Connected sessions / devices, on both clients: `get_connected_sessions()` → `list[ConnectedSession]`,
  `revoke_session(id)` and `revoke_all_sessions()` (`GET` / `DELETE /api/user-sessions`), verified against the real
  backend. A session is created per `x-device-id`, so pass a stable `device_id` to stay a single device.
  `ConnectedSession` carries the device id/model, app version, IP, geo (city/country/timezone/lat/long), status,
  `is_current`, creation and expiry, and the user id.
- The default `device_model` (sent as `x-device-model` and shown as the device name in the connected-devices list)
  is now `evdc-network-api` instead of an impersonated handset; override it with `device_model` to tell clients
  apart.
- `EvdcLiveClient` (`live` extra, `python-socketio`): live `chargingSessionProgress` updates as `SessionProgress`,
  with token refresh on socket authentication errors. Not yet tested on a real session.
- Two-factor login. When an account has 2FA enabled, `login()` raises `EvdcTwoFactorRequiredError` (carrying the
  `method`, `email` or `totp`) without activating the session, and the login is completed with `verify_two_factor()`,
  `verify_recovery_code()` or `resend_two_factor_code()`. The session is activated only after the code is verified.
  The `email` verification response shapes are not yet confirmed on a real account.
- API documentation in `docs/api.md`.
- Nearby charging points, on both clients. `get_nearby_stations(latitude, longitude, page, page_size)` returns one
  page from `/api/hubject/nearby/{longitude}/{latitude}` (longitude first, verified), nearest first.
  `find_stations_near(latitude, longitude, radius_m=2000, max_results=None)` walks the pages and stops at the radius,
  since the backend has no radius parameter, or after `max_results` when given. Verified on the real backend.
- `Evse` gains `name`, `status`, `distance_m`, `facilities` (`ChargingFacility`), `is_open_24h` and `max_power_kw`;
  `Pricing` gains `card_price`, `token_price`, `base_price`, `base_currency`, `parking_fee_enabled` and
  `parking_fee`.
