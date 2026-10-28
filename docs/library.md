# Library reference

How to use `evdc-network-api`: every public class, method, parameter, return type and exception. For the backend
endpoints behind each call see [api.md](api.md); for a quick start see the [README](../README.md).

All the data methods read **the authenticated user's own data** and never modify it, except the explicit
device-key and session-revocation calls in [Authentication](#authentication) and [Connected devices](#connected-devices).

## Contents

- [Quick start](#quick-start)
- [Clients](#clients)
- [Authentication](#authentication)
- [Charging history and sessions](#charging-history-and-sessions)
- [Stations](#stations)
- [Wallet](#wallet)
- [Notifications](#notifications)
- [Connected devices](#connected-devices)
- [Async client](#async-client)
- [Live progress](#live-progress)
- [Models](#models)
- [Exceptions](#exceptions)
- [Conventions](#conventions)

## Quick start

```python
from evdc_network_api import EvdcApiClient

with EvdcApiClient(email="you@example.com", password="...") as client:
    for s in client.iter_charge_history():
        print(s.started_at, s.energy_kwh, "kWh", s.cost, s.cost_currency)
```

The first call logs in by itself; an expired access token is refreshed, and a failed refresh falls back to a new login.
You never have to call `login()` explicitly unless the account has two-factor authentication (see below).

## Clients

### `EvdcApiClient`

Synchronous client built on `requests`. Usable as a context manager (closes the HTTP session on exit).

```python
EvdcApiClient(
    *, email, password=None, access_token=None, refresh_token=None, base_url=DEFAULT_BASE_URL, timeout=30,
    device_id=None, device_model="evdc-network-api", app_version="1.1.10", session=None,
    on_tokens_updated=None, device_key=None, user_id=None,
)
```

| Parameter | Type | Meaning |
|---|---|---|
| `email` | `str` | Account e-mail (required). |
| `password` | `str \| None` | Account password. Needed for a password login; not needed if you pass tokens or a device key. |
| `access_token`, `refresh_token` | `str \| None` | Tokens saved from a previous run, to skip the login. |
| `base_url` | `str` | Backend base URL (default `DEFAULT_BASE_URL`). |
| `timeout` | `int` | Per-request timeout in seconds. |
| `device_id` | `str \| None` | Stable device identifier sent as `x-device-id`. The backend keeps one login session per device id, so **reuse the same value across runs**; random if omitted. |
| `device_model` | `str` | Name shown for this client in the account's connected-devices list. |
| `app_version` | `str` | App version string sent with every request. |
| `session` | `requests.Session \| None` | Your own HTTP session (proxies, retries, …). |
| `on_tokens_updated` | `Callable[[str, str \| None], None] \| None` | Called with `(access_token, refresh_token)` whenever the tokens change; use it to persist them. |
| `device_key` | `str \| None` | Private-key PEM for [device-key login](#device-key-login-no-password-no-2fa). |
| `user_id` | `str \| None` | Account id; required together with `device_key`. |

Attributes: `email`, `access_token`, `refresh_token`, `user_id`, `device_id`, and the read-only property
`logged_in: bool`. Secrets are never included in `repr()` or in the log output.

`close() -> None` closes the HTTP session.

### `AsyncEvdcApiClient`

See [Async client](#async-client).

## Authentication

Automatic in normal use. Order of attempts when a token is missing or rejected (HTTP 401): refresh token → device key →
password login.

### `login() -> User`

Password login. Raises `EvdcAuthError` for wrong credentials or a missing password, and
`EvdcTwoFactorRequiredError` if the account has two-factor authentication (the session is **not** activated until the
code is verified). Accounts created with Google/Apple sign-in have no EVDC password and cannot use this.

### Two-factor authentication

```python
try:
    client.login()
except EvdcTwoFactorRequiredError as exc:
    print(exc.method)                     # "email" or "totp"
    client.verify_two_factor(input("code: "))
```

| Member | Returns | Description |
|---|---|---|
| `two_factor_pending` *(property)* | `str \| None` | `"email"`, `"totp"` or `None` when no code is awaited. |
| `verify_two_factor(code: str)` | `User` | Completes the login with the e-mail one-time code or the authenticator (TOTP) code. |
| `verify_recovery_code(code: str)` | `User` | Completes a pending **TOTP** login with a recovery code. |
| `resend_two_factor_code()` | `None` | Asks the backend to resend the e-mail code. |

All three raise `EvdcAuthError` if no verification is pending or the code is wrong.

### Token refresh

`token_refresh() -> None` gets a new access token from the refresh token (raises `EvdcAuthError` without one). It is
called automatically; call it yourself only if you want to refresh ahead of time. To keep tokens between runs:

```python
client = EvdcApiClient(
    email="you@example.com", password="...",
    access_token=saved_access, refresh_token=saved_refresh,
    on_tokens_updated=lambda access, refresh: save(access, refresh),
)
```

### Device-key login (no password, no 2FA)

For headless or long-running use. Enroll once while logged in, store the returned private key **outside the
repository**, and use it later.

| Method | Returns | Description |
|---|---|---|
| `enroll_device_key(device_key=None)` | `str` | Registers a key on the account (generates one if `device_key` is omitted) and returns its private-key PEM. Requires an authenticated session. |
| `login_with_device_key(device_key=None, *, fcm_token=DEFAULT_FCM_TOKEN)` | `User` | Logs in with the key. Needs the key and `user_id`. |
| `remove_device_key(device_key=None)` | `None` | Revokes the key on the account. |

`generate_device_key() -> str` (exported at package level) creates a new private-key PEM without touching the account.

## Charging history and sessions

| Method | Returns | Description |
|---|---|---|
| `get_charge_history(page=1, limit=10)` | `ChargingHistoryPage` | One page of completed sessions, 1-based, newest first. |
| `iter_charge_history(limit=10, max_pages=None)` | `Iterator[ChargingSession]` | The whole history, one page request at a time; stops after `max_pages` if given. |
| `get_ongoing_sessions()` | `list[OngoingSession]` | Sessions in progress; empty when not charging. |
| `get_receipt(session_id: str)` | `Receipt` | PDF receipt of a completed session. |
| `get_profile()` | `User` | The account profile. |

```python
for s in client.iter_charge_history(limit=50):
    print(s.started_at, s.energy_kwh, s.cost, s.cost_currency)

receipt = client.get_receipt(session.session_id)
Path(receipt.filename or "receipt.pdf").write_bytes(receipt.content)
```

`get_receipt` raises `EvdcApiError` when the payload carries no usable PDF.

### Amount vs cost

A session can be paid from the money wallet or the EVDC Token wallet. `amount` / `currency` is what left the wallet
(tokens, for a token-paid session); `cost` / `cost_currency` is the price in real money. **Use `cost` for cost
tracking.** For a money-paid session the two are equal; `token_conversion_rate` gives tokens per unit of
`cost_currency`.

## Stations

| Method | Returns | Description |
|---|---|---|
| `get_evse(evse_id: str)` | `Evse` | One charging point by EVSE id (e.g. `IT*ABC*E123*1`). |
| `get_favourite_stations()` | `list[Evse]` | The account's saved charging points, with live status and prices. |
| `get_nearby_stations(latitude, longitude, page=1, page_size=10)` | `list[Evse]` | One page of charging points around a point, nearest first. `page_size` is 1–100. Raises `ValueError` on invalid coordinates or paging values. |
| `find_stations_near(latitude, longitude, *, radius_m=2000, max_results=None)` | `list[Evse]` | Charging points within `radius_m` metres, nearest first. The backend has no radius, so pages are read until the first result beyond it. Keep the radius small: it is what bounds the number of requests. |

Each `Evse` is one **connector**: a station with two sockets appears twice. `distance_m` is set by the nearby calls.

## Wallet

| Method | Returns | Description |
|---|---|---|
| `get_wallets()` | `list[Wallet]` | Balances, e.g. a EUR wallet and the EVDC Token wallet. |
| `get_wallet_transactions(page=1, limit=10, *, currency=None, is_token=None)` | `WalletHistoryPage` | One page of movements, newest first. `currency` (e.g. `"EUR"`) and `is_token` filter the list. |
| `iter_wallet_transactions(limit=10, max_pages=None, *, currency=None, is_token=None)` | `Iterator[WalletTransaction]` | The whole wallet history. |

`WalletTransaction.session_id` links a payment to the charging session it settled.

## Notifications

| Method | Returns | Description |
|---|---|---|
| `get_notifications(page=1, limit=10, *, success=True)` | `NotificationPage` | One page, newest first. |
| `iter_notifications(limit=10, max_pages=None, *, success=True)` | `Iterator[Notification]` | All notifications. |
| `count_unread_notifications(*, success=True)` | `int` | Number of unread notifications. The backend has no count endpoint, so this pages through them all. |

## Connected devices

The logins ("sessions") of the account, one per device id.

| Method | Returns | Description |
|---|---|---|
| `get_connected_sessions()` | `list[ConnectedSession]` | Logged-in devices; the current one has `is_current=True`. |
| `revoke_session(session_id: str)` | `None` | Logs one device out. |
| `revoke_all_sessions()` | `None` | Logs out the connected devices. Whether the current one is kept is decided by the backend and not confirmed. |

## Async client

`AsyncEvdcApiClient(client)` wraps a sync client and runs each call in a worker thread (`asyncio.to_thread`), for
async frameworks such as Home Assistant or FastAPI. The underlying client is available as `.client`.

```python
from evdc_network_api import AsyncEvdcApiClient, EvdcApiClient

client = AsyncEvdcApiClient(EvdcApiClient(email="you@example.com", password="..."))
history = await client.get_all_charge_history()
await client.close()
```

Every method has the same name, parameters and return type as the sync client, with these differences:

| Sync | Async |
|---|---|
| `iter_charge_history(limit, max_pages)` | `get_all_charge_history(limit=10, max_pages=None) -> list[ChargingSession]` |
| `iter_wallet_transactions(...)` | `get_all_wallet_transactions(...) -> list[WalletTransaction]` |
| `iter_notifications(...)` | not wrapped: use `get_notifications` page by page |
| `two_factor_pending` | same, a plain property (not awaited) |

## Models

All models are `@dataclass(slots=True)`. Every API field is optional (`T | None`), because the backend omits fields
freely. Where present, `raw` holds the original payload (with tokens and passwords stripped); it is hidden from `repr()`.
Datetimes are timezone-aware UTC.

### `User`

`id`, `email`, `first_name`, `last_name`, `mobile`, `country_short_code`, `is_verified`, `is_two_factor_enabled`,
`two_factor_method`, `evco_id`, `rfid_method`, `company_name`, `vat_id`, `total_spending`, `last_visit_at`, `raw`.

### `ChargingSession`

| Field | Type | Meaning |
|---|---|---|
| `session_id`, `id`, `invoice_no` | `str \| None` | Identifiers; `session_id` is what `get_receipt` takes. |
| `evse_id` | `str \| None` | Charging point used; pass to `get_evse`. |
| `created_at`, `started_at`, `ended_at` | `datetime \| None` | Record creation, charging start, charging end. |
| `energy_kwh` | `float \| None` | Energy delivered. |
| `amount`, `currency` | `float \| None`, `str \| None` | What left the wallet; **tokens** for a token-paid session. |
| `cost`, `cost_currency` | `float \| None`, `str \| None` | Price in real money. |
| `token_conversion_rate` | `float \| None` | Tokens per unit of `cost_currency`; `1` for money-paid. |
| `operator` | `str \| None` | Station operator. |
| `is_paid`, `is_stopped`, `is_failed`, `is_test_session` | `bool \| None` | Status flags. |
| `charging_duration_minutes`, `time_fee` | `float \| None` | Charging time and any time-based fee. |
| `parking_duration_minutes`, `parking_fee` | `float \| None` | Parking after charging. |
| `time_surcharge_duration_minutes`, `time_surcharge_fee` | `float \| None` | Time surcharge. |
| `address` | `Address \| None` | Station address. |
| `pricing` | `Pricing \| None` | Tariff applied when billed (may differ from the station's current one). |
| `station` | `Evse \| None` | Station as embedded in the session. |

### `ChargingHistoryPage`

`sessions: list[ChargingSession]`, `page`, `limit`, `total_pages`, `total_documents`, and the property
`has_next: bool`.

### `OngoingSession`

`session_id`, `evse_id`, `amount`, `currency`, `created_at`, `is_paid`, `is_stop`, `raw`.

### `Receipt`

`filename: str | None`, `content: bytes` (the PDF; hidden from `repr()`).

### `Evse`

`evse_id`, `id`, `name`, `partner`, `operator_name`, `operator_id`, `status` (live: `Available`, `Occupied`,
`OutOfService`, `Unknown`, …), `distance_m`, `address: Address | None`, `latitude`, `longitude`, `plugs: list[str]`,
`facilities: list[ChargingFacility]`, `is_open_24h`, `pricing: Pricing | None`, `raw`, and the property
`max_power_kw: float | None`. Coordinates are as stored by the backend; a few records have latitude and longitude swapped.

### `Pricing`

A tariff per `unit` (e.g. `kWh`) in `currency`: `price` (wallet/token price, the app's default), `card_price`,
`token_price`, `base_price`, `base_currency`, `parking_fee_enabled`, `parking_fee`, `raw`.

### `ChargingFacility`

`power_kw`, `power_type` (`AC_1_PHASE`, `AC_3_PHASE`, `DC`), `voltage`, `amperage`.

### `Address`

`street`, `city`, `postal_code`, `region`, `state`, `country`.

### `Wallet`

`id`, `balance`, `currency`, `is_primary`, `is_token`, `currency_name`, `currency_symbol`, `decimals`,
`currency_type`, `raw`.

### `WalletTransaction` / `WalletHistoryPage`

`WalletTransaction`: `id`, `amount` (signed: negative for a payment, positive for a top-up), `currency`,
`description`, `category`, `is_token`, `old_balance`, `new_balance`, `session_id`, `created_at`, `raw`.

`WalletHistoryPage`: `transactions`, `page`, `limit`, `total`, `total_pages`, `closing_balances: dict[str, float]`
(per currency), `has_next`, `raw`.

### `Notification` / `NotificationPage`

`Notification`: `id`, `type`, `title`, `body`, `read`, `success`, `created_at`, `raw`.
`NotificationPage`: `notifications`, `page`, `total`, `total_pages`, `has_next`, `raw`.

### `ConnectedSession`

`id`, `device_id`, `device_model`, `app_version`, `ip`, `city`, `country`, `timezone`, `latitude`, `longitude`,
`status`, `is_current`, `created_at`, `expires_at`, `user_id`, `raw`.

### `SessionProgress`

Live progress update (`evse_id`, `time`, `session_start`, `charging_start`, `power_kw`, `max_power_kw`, `current_a`,
`max_current_a`, `energy_import_kwh`, `energy_export_kwh`, `consumed_energy_kwh`, `raw`, …). Match it to an
`OngoingSession` through `evse_id`, not the session id. Units follow the app's labels and are not confirmed on real
events. Delivered by [`EvdcLiveClient`](#live-progress).

## Live progress

`evdc_network_api.live.EvdcLiveClient` receives the progress of your ongoing sessions over the backend's socket. It
needs the optional extra: `pip install "evdc-network-api[live]"`.

```python
from evdc_network_api.live import EvdcLiveClient

live = EvdcLiveClient(client, on_progress=lambda p: print(p.evse_id, p.power_kw, "kW"))
live.connect()
live.wait()
```

| Member | Description |
|---|---|
| `EvdcLiveClient(client, on_progress, *, on_event=None)` | `client` is a sync `EvdcApiClient`; `on_progress(SessionProgress)` runs on the socket's background thread; `on_event(name, args)` receives any other server event (debugging). Raises `EvdcApiError` if the extra is missing. |
| `connect()` | Opens the socket, logging in or refreshing first if needed. |
| `wait()` | Blocks until disconnected. |
| `disconnect()` | Closes the socket. |
| `connected` *(property)* | `bool`. |

## Exceptions

```
EvdcApiError                      base; .status_code is the HTTP status when it comes from a response
└── EvdcAuthError                 bad credentials, expired session, social-only account, HTTP 401
    └── EvdcTwoFactorRequiredError  login needs a code; .method is "email" or "totp"
```

Network failures (timeouts, connection errors) are raised as `EvdcApiError` without a status code. A 401 on a data
call is retried once after re-authentication before `EvdcAuthError` reaches you.

## Conventions

- **Units:** energy in kWh, power in kW, distances in metres, durations in minutes.
- **Pagination:** `page` is 1-based; `iter_*` methods walk all pages lazily and accept `max_pages`.
- **Rate:** the client makes one request per call. Don't poll aggressively and keep nearby searches to a small radius.
- **Secrets:** tokens, passwords and device keys are never logged nor kept in `raw`; keep tokens and keys outside the
  repository.
