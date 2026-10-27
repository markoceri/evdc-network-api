# evdc-network-api

[![License](https://img.shields.io/github/license/markoceri/evdc-network-api)](https://github.com/markoceri/evdc-network-api/blob/main/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/type--checked-mypy-blue.svg)](https://mypy-lang.org/)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20me-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/markoceri)

Unofficial Python client for the [EVDC](https://evdc.network) EV charging network API.

> [!IMPORTANT]
> This project is **not affiliated with, endorsed by, or supported by EVDC** or its developers.
> It is an independent interoperability project. Read the [legal notice](LEGAL.md) before using or contributing.

## Purpose

EVDC keeps a log of the user's charging sessions — duration, energy delivered and cost — but offers no public API
to retrieve it. This library gives an EVDC account holder programmatic access to **their own** charging data, so it
can be imported into other tools.

A typical use is charging cost tracking: vehicle or home-automation software often knows when and how much a car
charged, but not what each session **cost** at a public charger. With this library such software can match its
charging sessions with the EVDC sessions and attach the price paid to each of them.

```
 EVDC cloud ──► evdc-network-api ──► your application
               (sessions, kWh, cost)
```

## Scope

In scope:

- authentication with the user's own EVDC credentials;
- charging session history: start and end time, station, energy delivered, cost, currency;
- the data needed to read the history (account, station and tariff details).

Out of scope, and not accepted as contributions:

- starting, stopping or paying for charging sessions on behalf of third parties;
- access to any data other than the authenticated user's own;
- circumventing payment, tariffs, rate limits, or any technical protection measure;
- redistribution of EVDC code, assets, keys or certificates;
- bulk scraping of stations, prices or other network-wide data.

## How the interface is documented

The API is documented by observing the traffic between the official EVDC app and its backend, while using the app
with the author's own lawfully held account, and by studying the app only as far as needed to understand the data
format exchanged with the server. Only the information strictly needed for interoperability is recorded in this
repository, under [`docs/`](docs/). See the [legal notice](LEGAL.md) for the European legal framework this relies on.

## Status

🚧 Alpha. Login, token refresh, the account profile, the charging history and its sessions, the PDF receipt and the
station details are verified against the real backend. Ongoing sessions and live socket progress are still
reconstructed from the app and not yet confirmed on a live charge; the original payload is always kept in `raw`.

Email/password accounts are supported, including those with two-factor authentication (an e-mail code or an
authenticator app): `login()` raises `EvdcTwoFactorRequiredError` and the login is completed with a verification
code (see below). Accounts created with Google or Apple sign-in have no EVDC password and cannot log in through the
API.

## Installation

Not yet published on PyPI. From a clone:

```bash
pip install -e .            # client
pip install -e ".[live]"    # plus live session progress (python-socketio)
```

## Usage

```python
from evdc_network_api import EvdcApiClient

with EvdcApiClient(email="you@example.com", password="...") as client:
    for session in client.iter_charge_history():
        print(session.created_at, session.energy_kwh, "kWh", session.amount, session.currency, session.evse_id)

    for ongoing in client.get_ongoing_sessions():
        print("charging on", ongoing.evse_id, "since", ongoing.created_at)

    receipt = client.get_receipt(session_id)  # PDF bytes in receipt.content

    for wallet in client.get_wallets():
        print(wallet.currency, wallet.balance)  # e.g. EUR 41.97, and the EVDC Token wallet
    for txn in client.iter_wallet_transactions():
        print(txn.created_at, txn.amount, txn.currency, txn.session_id)  # session_id links a payment to a session
```

Charging points around a position (for example the vehicle's), nearest first, with live status and prices:

```python
for evse in client.find_stations_near(45.4642, 9.1900, radius_m=1000):
    p = evse.pricing
    print(
        f"{evse.distance_m:.0f} m",
        evse.operator_name,
        evse.status,
        evse.max_power_kw,
        "kW",
        p.price,
        p.currency,
        "/",
        p.unit,
        "(card:",
        p.card_price,
        ")",
    )
```

Each result is one connector (EVSE). All the connectors within the radius are returned; pass `max_results` to
stop earlier. Search one position at a time with a local radius: sweeping an area is out of the project's scope.

If the account has two-factor authentication, complete the login with the code it asks for:

```python
from evdc_network_api import EvdcApiClient, EvdcTwoFactorRequiredError

client = EvdcApiClient(email="you@example.com", password="...")
try:
    client.login()
except EvdcTwoFactorRequiredError as exc:
    code = input(f"Enter the {exc.method} verification code: ")  # e-mail code or authenticator code
    client.verify_two_factor(code)
# the client is authenticated from here on
```

`exc.method` is `"email"` (a code e-mailed on login) or `"totp"` (an authenticator app); `verify_two_factor()`
handles both. For an authenticator account you can use a recovery code instead with `verify_recovery_code(code)`.
The verification endpoints and payloads are in [`docs/api.md`](docs/api.md).

The account's logged-in sessions (devices) can be listed and revoked. A session is created per device id, so pass a
**stable** `device_id` (a 64-hex string kept across runs) to stay one device instead of registering a new one each
login. The session shows up under `device_model` (default `evdc-network-api`); set `device_model` to tell clients
apart:

```python
for s in client.get_connected_sessions():
    print(s.device_model, s.city, s.country, "(this device)" if s.is_current else "")
client.revoke_session(session_id)  # log one device out
client.revoke_all_sessions()  # log the other devices out
```

The client logs in on the first call and refreshes the access token by itself. To avoid a new login at every start,
persist the tokens and the device id:

```python
client = EvdcApiClient(
    email="you@example.com",
    password="...",
    device_id=saved_device_id,  # stable 64-hex id
    access_token=saved_access_token,
    refresh_token=saved_refresh_token,
    on_tokens_updated=lambda access, refresh: save(access, refresh),
)
```

For long-running or headless use, a **device key** avoids re-doing two-factor every time the refresh token lapses.
Enrol one once (from an authenticated session), persist the returned private key **outside the repository** next to
the account id, and log in with it afterwards — no password, no 2FA:

```python
# once, while logged in:
device_key = client.enroll_device_key()  # returns the private-key PEM; save it securely
save(device_key, client.user_id)

# later, in a fresh process:
client = EvdcApiClient(email="you@example.com", device_key=saved_device_key, user_id=saved_user_id)
client.get_profile()  # logs in via the device key automatically
client.remove_device_key()  # revoke it when no longer needed
```

The private key is a long-term login credential that bypasses two-factor: store it like a password and revoke it if
it leaks.

An async wrapper is available as `AsyncEvdcApiClient(client)`, and live progress of an ongoing session as
`evdc_network_api.live.EvdcLiveClient`. See [`examples/`](examples/) and the API notes in [`docs/api.md`](docs/api.md).

## Legal

- [Legal notice and interoperability statement](LEGAL.md)

## License

This project is licensed under the [GNU Affero General Public License v3.0](LICENSE).
