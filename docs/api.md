# EVDC backend API

Notes on the interface between the official EVDC Android app and its backend, collected for interoperability
(see [LEGAL.md](../LEGAL.md)). Only what is needed to read the authenticated user's own data is documented here.

> Status: request shapes come from the decompiled client. Login, token refresh, profile, system configuration, the
> history / ongoing-session envelopes, the history items, the receipt and the EVSE detail are **verified** against the
> real backend. The ongoing-session item and the socket progress event are verified on a real charge too. Everything marked
> *inferred* is still to be confirmed. See [Changes in app 2.2](#changes-in-app-22-checked-2026-11-25).

## Source

| Item | Value |
|---|---|
| Package | `com.network.evdc.app` |
| Version analysed | 1.1.10 (version code 82) |
| Framework | React Native, Hermes bytecode v96 (`assets/index.android.bundle`), CodePush OTA updates |
| HTTP client | axios |

Because the app uses CodePush, the JavaScript logic can change without a new APK version.

## Base URL

```
https://api-v2.evdccharge.co/
```

Taken from the `API_URL` build config value. All paths below are relative to it.

## Common headers

A request interceptor adds these headers to every call made through the shared axios instance:

| Header | Value |
|---|---|
| `Accept` / `Content-Type` | `application/json` |
| `Authorization` | `Bearer <accessToken>`, only when logged in |
| `req-scope` | `MOBILEMED-FE` (constant) |
| `x-device-id` | Stable per-device id: 64 hex chars. The app derives it as HMAC-SHA256 of the Android ID with an app-embedded key, so any stable random 64-hex value should be equivalent. |
| `x-user-id` | `_id` of the logged-in user, when known |
| `x-device-model` | Free text; shown as the device name in the connected-devices list. The app sends `<os>-<osVersion>-<brand>-<model>` (e.g. `Android-14-Google-Pixel 8`); this library defaults to `evdc-network-api`. |
| `x-app-version` | App version, e.g. `1.1.10` |
| `x-request-id` | Random UUID v4 per request |

Requests time out after 600 s in the app.

## Authentication

### Login — `POST /api/signIn-enc`

```json
{ "email": "user@example.com", "password": "<base64 RSA-OAEP ciphertext>" }
```

The password is encrypted client-side:

- RSA public key from the `PASSWORD_ENC_KEY` build config value (PEM, RSA-2048);
- padding **RSA-OAEP**, hash **SHA-256**, MGF1 **SHA-256**;
- plaintext: UTF-8 password; output: base64.

If encryption fails, the app falls back to `POST /api/signIn` with the same body and the plaintext password.
Whether the server still accepts the plaintext endpoint has not been verified.

The body may also carry an `fcmToken` (push notifications), which this library does not need.

Response (shape inferred from the client):

```json
{
  "data": {
    "accessToken": "<jwt?>",
    "refreshToken": "<opaque?>",
    "...": "user fields, including _id"
  }
}
```

### Two-factor verification

When the login response reports `isTwoFactorEnabled: true` (with `twoFactorMethod` either `email` or `totp`), the
login is completed with a verification code before the session is used. The method drives which endpoint is called:

| Method | Endpoint | Body |
|---|---|---|
| `email` | `POST /api/verifyOTP` | `{ "email", "otp", "isTwoFactorEnabled": true }` |
| `email` (resend) | `POST /api/resendVerificationCode` | `{ "email", "isForgotPassword": false }` |
| `totp` | `POST /api/2fa/totp/login` | `{ "email", "totpCode" }` |
| `totp` (recovery) | `POST /api/2fa/totp/recovery-login` | `{ "email", "recoveryCode" }` |

Both methods are **verified** against the real backend. The two endpoints differ in how they authenticate and where they
put the tokens:

- **`email`** — `POST /api/verifyOTP` is **unauthenticated** (no bearer). A correct code returns HTTP 200 with the
  user and fresh tokens nested under `user`; a wrong code returns HTTP 400.
  ```json
  { "user": { "...user fields...", "accessToken": "…", "refreshToken": "…" },
    "message": "Verification code verified successfully." }
  ```
- **`totp`** — `POST /api/2fa/totp/login` (and `/recovery-login`) **require** the pre-2FA token that `signIn-enc`
  returns, sent as `Authorization: Bearer`. Without it the server answers HTTP 401 `No auth token`. The response is
  the **user object at the root** (not nested), with `accessToken` / `refreshToken` / `token`.

So `signIn-enc` returns a token even when 2FA is pending: for `email` it is only held by the client, for `totp` it
is also needed to authorise the verification call. The client holds it either way and exposes `verify_two_factor()`,
`verify_recovery_code()` and `resend_two_factor_code()`, reading the tokens from `user`, `data` or the root.

### Biometric device-key login (long-term, no password / 2FA) — **verified**

The app's "biometric login" is a device-bound key pair: the fingerprint only unlocks the private key locally. The
same scheme works for a headless client that holds the private key itself, giving a durable login that needs no
password and no 2FA.

- **Enroll** (while authenticated): `PUT /api/profile { "biometricKey": "<base64 DER SPKI public key>" }`. The
  server **appends** the key to the account's `biometricKeys` **list** (it does not replace existing keys, so every
  device keeps its own). `PUT /api/profile` **merges** (the app sends only the edited fields), so sending just
  `biometricKey` leaves the rest of the profile untouched. `GET /api/profile` does **not** return `biometricKeys`
  (the biometric-login response does).
- **Login**: `POST /api/biometric-login` (unauthenticated) with
  ```json
  { "fcmToken": "<non-empty>", "signature": "<base64>", "payload": "<epoch seconds>", "userId": "<_id>" }
  ```
  `payload` is `Math.round(Date.now()/1000)` as a string; `signature` is RSA **PKCS#1 v1.5 over SHA-256** of the
  payload bytes, base64. There is **no device identifier** in the body — the server verifies the signature against
  **any** key in the account's `biometricKeys`. `fcmToken` must be non-empty but is not otherwise used (a constant
  works; it does not overwrite the real push token). Response (HTTP 200): tokens at the **root** (`accessToken`,
  `refreshToken`, `token`) plus the account under `user`. The access token lasts 5 minutes; a refresh token too.
- **Remove**: `POST /api/remove-biometricKey { "biometricKey": "<base64 DER SPKI public key>" }`.

Key format is what `react-native-biometrics` produces: RSA-2048, public key as base64 of the DER
SubjectPublicKeyInfo. The client exposes `enroll_device_key()`, `login_with_device_key()` and `remove_device_key()`,
and `generate_device_key()`; a client built with `device_key` + `user_id` logs in through this path automatically.

### Token refresh — `POST /api/refresh-token`

```json
{ "refreshToken": "<refreshToken>" }
```

The call goes to `API_URL + "api/refresh-token"` through a separate axios instance, without the auth interceptor.

Response (**verified**): HTTP 200 with `{ "accessToken": "<jwt>" }` at the top level, no `data` envelope. The refresh
token is not rotated. When the current access token is still valid, the same token may come back.

App behaviour on **HTTP 401**: refresh once (`_retry` flag), queue concurrent requests in the meantime, replay them
with the new token. If there is no refresh token or the refresh fails, the app logs out.

### Other account endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/api/profile` | Current user profile |
| POST | `/api/signOut` | Logout |
| PUT | `/api/profile` | Update the profile (merge); also enrols a biometric key via `{ "biometricKey" }`, **verified** |
| POST | `/api/biometric-login` | Device-key login, no password/2FA, **verified** |
| POST | `/api/remove-biometricKey` | Revoke a biometric key, **verified** |
| GET | `/api/favourite/stations` | The account's favourite stations (`{ "result": { "data": [ … ] } }`), **verified** |
| GET | `/api/notification/?page=&limit=&success=` | Notifications (`result.data.data[]`), **verified** |
| GET | `/api/user-sessions` | List the account's logged-in sessions / devices (`{ "data": [ … ] }`), **verified** |
| DELETE | `/api/user-sessions/{id}` | Revoke one session by its `_id`, **verified** |
| DELETE | `/api/user-sessions` | Revoke all sessions (current one included), **verified** |

Each session item (**verified**) carries `_id`, `deviceId`, `deviceModel`, `appVersion`, `ip`, `city`, `country`,
`timezone`, `latitude`, `longitude`, `status`, `isCurrent`, `createdAt`, `expiresAt` and `user` (plus a server-side
`refreshTokenEncrypted`). A session is created per distinct `x-device-id`, so reusing a stable device id keeps the
client as a single device instead of a new one each login; `expiresAt` is ~7 days after login.

Revocation semantics (**verified**): `DELETE /api/user-sessions` removes **every** session, the current one too.
It invalidates the refresh tokens (a later `refresh-token` returns 401), but an already-issued **access token keeps
working until it expires** — revoking a session does not kill its live access token. The client exposes
`get_connected_sessions()`, `revoke_session(id)` and `revoke_all_sessions()`.

## Charging sessions

### History — `GET /api/hubject/charge-history`

Query parameters: `page` (1-based) and `limit`.

Response envelope (**verified**): `{ "page", "limit", "totalPages", "totalDocuments", "data": [ … ] }`. The item
fields are in [ChargingSession](#chargingsession--history-item-get-apihubjectcharge-history--data), now **verified**
against the real backend. Notable: `consumedEnergy` (kWh); `timeDetails` (`durationInMinutes`), `invoiceNo` (which equals
the receipt filename) and `notificationDetails` (`chargingStart` / `chargingEnd`) give the timing; status is in
`isPaid` / `isStop` / `isSessionFailed` / `isTestSession`.

**Cost vs. amount (important for token-paid sessions).** The top-level `amount` / `currency` is what left the
wallet — for a token-paid session that is in tokens (e.g. `"EVDC Token"`), not money. The real-money price is in
`pricingDetails`: `chargingPrice` with `Currency`, and `tokenConversionRate` relates the two
(`amount ≈ chargingPrice × tokenConversionRate`, and the rate is `1` for a money-paid session). Verified: a token
session showed `amount` 352160.89 EVDC Token, `chargingPrice` 6.81 EUR, rate 51712.32. The library surfaces these as
`cost` / `cost_currency` / `token_conversion_rate`. The `tokenConversionRate` lives only on the session;
`GET /api/wallet/currencies` lists the fiat currencies (EUR, USD) and Stripe fees, not the tokens or any rate.

### Receipt — `GET /api/hubject/download-pdf/{sessionId}`

Returns the session's PDF receipt as JSON `{ "base64", "filename" }`, **verified**: `filename` is `<invoiceNo>.pdf`
and the decoded bytes are a real PDF.

### Ongoing sessions — `GET /api/hubject/ongoing-sessionsV2`

No parameters. Returns the user's sessions that are currently in progress (the app's "ongoing sessions" screen, also
refreshed on pull-to-refresh and when a push notification arrives). **Verified** on a real public-station charge: the
response is a bare array whose items have the same shape as a charging-history entry (`sessionId`, `evseId`,
`invoiceNo`, `pricingDetails`, `operator`, `protocol`, …). It is `[]` when nothing is charging.

Observed lifecycle of one item:

1. Right after the session is created: `isChargingStarted: false`, `amount: 0`, `notificationDetails` empty.
2. When energy starts flowing: `isChargingStarted: true` and `notificationDetails.chargingStart` is set.
3. While charging, only `updatedAt` changes: `amount` stays `0` and `timeDetails`, `ocpiCostBreakdown` and
   `reconciled_data` stay `null`. Energy and cost are not in this endpoint — use the socket events for live energy.
4. When the session ends the item disappears from the list and appears in the charge history with the final
   energy, cost and `isPaid` / `isStop` set. The last socket energy (23.687 kWh) matched the history value
   (23.707 kWh) to within the last interval.

The tariff is in `pricingDetails` (`costKwh`, `Price`, `PreAuthHoldAmount` — the amount held as pre-authorisation —
and `parkingPricing`).

Session lifecycle states seen in the client: `SESSION_STARTED`, `SESSION_STOPPED`, `SESSION_PAID`, `SESSION_FAILED`.

## Wallet (read-only) — **verified**

The account's balances and the movements that paid for charging, in EUR and in the `EVDC Token` wallet.

- **Balances** — `GET /api/wallet/user/wallets` → `{ "result": { "data": [ Wallet ], "count" } }`. Each wallet:
  `_id`, `balance`, `currency`, `isPrimary`, `isToken`, and `currencyDetails` (`name`, `symbol`, `decimals`,
  `type` = `FIAT` / `TOKEN`).
- **Transactions** — `GET /api/wallet/history?page=&limit=&currency=&isToken=` →
  `{ "data": [ Transaction ], "total", "page", "limit", "totalPages", "balances": [ { currency, closingBalance } ] }`.
  Each transaction: `transactionAmount` (signed — negative for a payment, positive for a top-up), `currency`,
  `description`, `category` (e.g. `charging`, `transfer`), `isToken`, `oldBalance`, `newBalance`, `createdAt`, and
  `metaData.sessionId` linking a charging payment to its session.
- Currencies reference: `GET /api/wallet/currencies`.

The client exposes `get_wallets()`, `get_wallet_transactions()` and `iter_wallet_transactions()`. Top-ups, transfers
and setting the primary wallet are write operations and are out of scope.

Undocumented fields seen on real responses (they are kept in `raw`, not modelled):

- **Wallet** — `chargeCurrency`, `blockchain` (`null` for non-token wallets) and `fee` (`percentage`, `fix`,
  `international`, `country`).
- **Transaction** — `fromCurrency` (e.g. `EVDC Token` when a payment converted tokens), `baseEUR`, `remainingEUR`,
  `originalBalance`, `remainingMigrationCredit`, `isFraud`, `note` and `transactionId` (often `null`).
- **Export** — `GET /api/wallet/history/export-pdf` (app 2.2) returns `{ "result": { "filename", "base64" } }`: the
  account's wallet history as a PDF (verified, `%PDF-`, ~100 KB for a small account; no parameters needed). The
  client exposes `export_wallet_history()`, which returns the same `Receipt` shape as `get_receipt()`.

## Changes in app 2.2 (checked 2026-11-25)

The 2.2 APK (version code 88) was compared with 1.1.10 (82). The bundle is Hermes bytecode, format 96 → 98.

- **Compatible:** every endpoint the client uses is still present and answers identically with `x-app-version` set to
  `1.1.10` or `2.2` (same status, same fields for profile, history, ongoing, wallets, transactions, notifications,
  favourites and connected sessions). `DEFAULT_APP_VERSION` was not changed.
- **New in the bundle:** `banners`, `faq`, `refund-requests` (+ `create`, `cancel`), `route-planner/*`,
  `user-vehicles` (+ `image`), `wallet/convert`, `wallet/history/export-pdf`, `hubject/session/top-frequent-chargers`
  and `signUp/v2`.
- **Removed:** `rfid/orders/get`, `supportMail-v2`, `media/upload`, `wallet/add/balance/usd` (+ `confirm`),
  `wallet/add/token` and the old `signUp-enc`.
- **Read-only endpoints verified on the real backend:**
  - `GET /api/hubject/session/top-frequent-chargers?limit=` → `{ "data": [ { "evseId", "count", "lastUsedAt",
    "evseData": { "EvseData": { … } } } ] }`: the stations the user charged at most (`count` sessions, last use). The
    `evseData` is the usual `EvseData` record without live price or status. Exposed as `get_frequent_chargers()`.
  - `GET /api/user-vehicles` → `{ "data": [] }` and `GET /api/refund-requests` → `{ "data": [], "total", "page",
    "limit", "totalPages" }`. Both were empty on the test account, so the item shapes are **not verified** and they
    are not modelled. Creating, updating or cancelling vehicles and refund requests, the route planner and wallet
    conversion are out of scope.

## Favourite stations and notifications (read-only) — **verified**

- **Favourites** — `GET /api/favourite/stations` → `{ "result": { "data": [ { "EvseID", "status", "isFavourite",
  "station_data": { …EvseData… } } ] } }`. Each item wraps the EVSE under `station_data`; the client maps it to an
  `Evse` (with live `status` and prices) via `get_favourite_stations()`.
- **Notifications** — `GET /api/notification/?page=&limit=&success=` → `{ "result": { "data": { "data":
  [ Notification ], "total", "currentPage", "totalPages" } } }`. `success` is **required** and must be a lowercase
  boolean string (`"true"` / `"false"`; Python's `"True"` is rejected). Each notification: `_id`, `type`, `title`,
  `body`, `read`, `success`, `createdAt`. The client exposes `get_notifications()` and `iter_notifications()`.
- **Unread count**: `/api/notification/unread-count` is referenced by the app but **returns HTTP 404** on the
  backend (no such route), so `count_unread_notifications()` pages the list and counts `read == false` instead.

## Real-time session progress (socket.io)

The app opens a socket.io connection to receive live progress of ongoing sessions.

| Item | Value |
|---|---|
| URL | `API_URL` (`https://api-v2.evdccharge.co/`), default path `/socket.io/` |
| Transport | `websocket` only |
| Auth | query parameter `token=<accessToken>` |
| Reconnection | infinite attempts, delay 1–5 s, randomization 0.5 |

Flow:

1. Connect with the current access token. The socket only connects for a logged-in user (one with `_id`).
2. On `connect`, the client emits `register` with no payload, then `getTotalUnreadChatsCount` (chat, not needed).
3. The server pushes `chargingSessionProgress` events.
4. On `connect_error` with message `Authentication error`, the client reconnects with the latest stored access
   token. When the token is refreshed over HTTP, the socket is disconnected and reopened with the new token.

`chargingSessionProgress` payload — **verified** on a real charge. It follows the Hubject OICP charging-notification
model (PascalCase) and carries both the session and the EVSE:

| Field | Observed value |
|---|---|
| `Type` | `"Progress"` |
| `SessionID`, `CPOPartnerSessionID` | Session ids (`SessionID` equals the ongoing session's `sessionId`); `EMPPartnerSessionID` is `null` |
| `OperatorID`, `EvseID` / `evseId` | Operator and EVSE of the session |
| `ChargingStart` | ISO timestamp charging began (`SessionStart` was `null`) |
| `EventOccurred` | ISO timestamp of this event (there is no `Time`) |
| `ConsumedEnergyProgress` | Energy delivered so far, kWh (cumulative) |
| `MeterValueStart` | Meter reading at the start, kWh |
| `Identification.RemoteIdentification` | Identifier used to start the session (personal: do not log) |
| `Timeline[]` | One point per event so far: `{ timestamp, value, current, power, maxPower, minPower, maxCurrent, minCurrent, stateOfCharge, time, parkingTime, reservationTime, energyExport, energyImport }`; `value` is the consumed energy, the others were `null` |
| `ChargingDuration`, `MeterValueInBetween`, `PartnerProductID`, `Protocol` | `null`, `null`, product label, `HUBJECT` |

Cadence on the observed station: one event about every 5 minutes (8 events in ~37 minutes, 2.5 → 23.7 kWh). Power
and current were **not** reported (all `null`), so derive power from consecutive `ConsumedEnergyProgress` values. Some
stations may report them in `Power` / `Current` or in the timeline. The socket also pushes `totalUnreadChatsCount`
after `register`, which can be ignored.

The app adds a local `receivedAt` timestamp and keeps only the latest event per `evseId`. Events are pushed when the
charge point operator sends progress notifications through Hubject. Some stations may never send them; for that case
the app shows a "waiting for live data" placeholder and treats data as stale after a while. Exact types and units
are **to be confirmed** with a capture.

Only reading the user's own session is in scope. Remote start/stop and connector unlock are not.

## Stations

| Method | Path | Notes |
|---|---|---|
| GET | `/api/hubject/{evseId}` | Single EVSE details (schema TBD) |
| GET | `/api/hubject/nearby/{longitude}/{latitude}?page=&pageSize=` | Charging points around one point, **verified** |

### Nearby charging points — `GET /api/hubject/nearby/{longitude}/{latitude}`

Used by the app's "near me" list. **Verified.**

- **Longitude first** in the path (GeoJSON order). With the values swapped the search runs around a different point
  and returns far-away results, so the order matters.
- Query: `page` (1-based) and `pageSize`, both to be sent: without `pageSize` the backend fails with HTTP 500
  (`invalid argument to $limit stage`), as it has no default. The app asks for 5 per page; the backend honours
  larger pages (verified up to 200, with consistent pagination), and `find_stations_near` reads 50 at a time.
- No radius, bounding box or filter parameter: results come **sorted by distance**, nearest first. A radius is
  applied by the client, by stopping at the first item farther than it.
- Response: `{ "result": [ …Evse… ] }`, no pagination counters; a page shorter than `pageSize` is the last one.
- Each item is **one EVSE (connector)**, so a station with two sockets appears twice (`…*1`, `…*2`). Items carry
  `distance` (metres from the point), `status` and `pricingDetails`, so prices need no extra request.
- Data quality: a few records have latitude and longitude swapped in `EvseData.GeoCoordinates` and in `location`.
  The search compares the query against `location`, so those stations never show up around their real position.

Search **one point at a time**, as the app does. Sweeping an area with many points, or the bulk endpoints
(`/api/hubject/stations/by-ip-location`, `/api/hubject/sync/evse`), is out of scope. `find_stations_near` reads
pages until the radius is exceeded (optionally until `max_results`), so the radius bounds the number of requests;
it also stops if a page brings nothing new.

## Data models (inferred)

Reconstructed from the properties the app reads when rendering each object. TypeScript types do not survive
compilation, so:

- field **names and nesting** are reliable;
- **types** are guesses from usage (numbers formatted with units, dates parsed, booleans in conditions);
- fields the app never reads are **missing** (the real payloads are probably larger).

Station fields in PascalCase follow the Hubject OICP 2.3 EVSE data model (`EvseDataRecord`); camelCase fields are
EVDC's own.

### Response envelopes

**Verified against real responses.** Envelopes are **not
uniform** — each endpoint has its own shape:

| Endpoint | Envelope |
|---|---|
| `POST /api/signIn-enc` | `{ "data": { …user fields…, "accessToken", "refreshToken", "token" } }` — user and tokens in the **same** object, not nested under `data.user` |
| `GET /api/profile` | the User object **directly**, no wrapper |
| `GET /api/system-configuration` | `{ "data": [ …config… ] }` |
| `GET /api/hubject/charge-history` | `{ "page", "limit", "totalPages", "totalDocuments", "data": [ …items… ] }` (pagination envelope) |
| `GET /api/hubject/ongoing-sessionsV2` | a bare JSON **array** `[ … ]` |

So the client needs a small per-endpoint unwrap, not one global rule. Error responses look like
`{ "message": "…", "errors": [] }` with a 4xx status. The socket `chargingSessionProgress` payload, by contrast, is
wrapped as `response.data.result.data` inside the event (seen only in the bytecode).

### User (`GET /api/profile`, and login `data`) — **confirmed**

Real response fields (login `data` and `/api/profile` share the core; profile adds a few). Optional fields come back
`null` when unset.

| Field | Type | Notes |
|---|---|---|
| `_id` | str | 24-hex Mongo id; used as `x-user-id` header |
| `email` | str | |
| `firstName`, `lastName` | str | |
| `mobile` | str | Phone (empty string when unset) |
| `countryCode`, `countryShortCode` | str\|null | e.g. `BE` |
| `googleId`, `facebookId`, `appleId` | str\|null | Set when the account is linked to that social login |
| `isVerified`, `isAdmin`, `isAdminVerified` | bool | |
| `isTwoFactorEnabled` | bool | |
| `twoFactorMethod` | str\|null | `email` or `totp`; drives the 2FA login step |
| `force2FA` | bool | *(profile only)* server asking to enable 2FA |
| `guestId` | str\|null | Guest accounts |
| `evcoId` | str | E-mobility contract id (EVCO), e.g. `XX-YYY-…` |
| `rfidMethod` | str | e.g. `WALLET` |
| `stripe_customer_id` | str\|null | Stripe customer |
| `isSaveCard`, `defaultCardId` | bool / str\|null | Saved payment card |
| `notificationEnabled`, `fcmToken`, `fcmTokens[]` | bool / str | Push |
| `isDefaulter` | bool | Has unpaid balance |
| `openEclearingSession`, `hubjectSession` | obj\|null | Pointer to a live charging session, if any |
| `companyName`, `companyAddress`, `vatId`, `taxIdNumber`, `pecEmail`, `street`, `city`, `province`, `postalCode`, `taxType` | str\|null | Invoicing / billing details |
| `totalSpending`, `totalSpendingToken` | number | *(profile only)* lifetime spend |
| `tokenBalanceInUSD`, `tokenBalanceInLocalCurrency` | number | *(profile only)* wallet token balance |
| `geolocation` | obj | *(profile only)* IP geo: `country`, `timezone`, `ll[lat,lng]`, `currency`, … |
| `activeMembership` | array | *(profile only)* |

Login `data` additionally carries `accessToken`, `refreshToken` and a legacy `token`.

### SystemConfiguration (`GET /api/system-configuration`) — **confirmed**

`data` is an array of feature flags, each `{ _id, systemConfigKey, description, value, createdAt, updatedAt, __v }`
where `value` is `{ whitelisted: {status, userIds[]}, blacklisted: {status, userIds[]} }`. Keys seen:
`Show_Route_Planner`, `testmode`, `Wallet_V2`, `Wallet_ShowCard`, `Show_Rfid_Orders`, `Show_Skip_2FA`,
`Show_Email_2FA`. Not needed to read sessions; kept for reference.

> **Verified against the real backend:** `ChargingSession` (history item), the receipt PDF payload and the `Evse` detail
> (`GET /api/hubject/{evseId}` → `{ "result": { … } }`). `OngoingSession` and the socket progress event were verified later on a running session. `ChargingSession` nests the applied tariff in `pricingDetails`, the billed station in
> `chargingStation` (same `EvseData` shape as the EVSE detail) and its address in `evseDetails`.

### ChargingSession — history item (`GET /api/hubject/charge-history` → `data[]`)

| Field | Type | Notes |
|---|---|---|
| `_id` | str | EVDC record id |
| `sessionId` | str | Hubject session id. Key for the receipt PDF. |
| `evseId` | str | EVSE where the session ran (OICP EVSE ID, e.g. `IT*ABC*E123*1`) |
| `invoiceNo` | str | |
| `createdAt` | ISO datetime | Session date shown in the list |
| `amount` | number | Total cost |
| `currency` | str | e.g. `EUR` |
| `consumedEnergy` | number | kWh (also under `pricingDetails`) |
| `time` | ? | |
| `operator` | str | Operator name |
| `company` | ? | |
| `location` | ? | |
| `pricingDetails` | Pricing | Tariff applied, see below. Also carries `consumedEnergy`. |
| `timeDetails` | object | `durationInMinutes`, `timeFee` (time-based fee) |
| `parkingDetails` | object | `durationInMinutes`, `parkingFee` |
| `timeSurchargeDurationInMinutes`, `timeSurchargeFee` | number | Overstay surcharge |
| `evseDetails.address` | object | `Street`, `City`, `PostalCode`, `Region`, `State`, `Country` |
| `chargingStation` | Evse | Embedded station record (`EvseData.Address`, `EvseData.OperatorName`, …) |

The app pages with `limit = PAGE_SIZE` (probably 10) and stops when a page returns fewer items.

### Receipt (`GET /api/hubject/download-pdf/{sessionId}`)

| Field | Type | Notes |
|---|---|---|
| `base64` | str | PDF file, base64-encoded |
| `filename` | str | Suggested file name |

### OngoingSession (`GET /api/hubject/ongoing-sessionsV2` → bare array)

| Field | Type | Notes |
|---|---|---|
| `sessionId` | str | |
| `evseId` | str | Join key with live progress |
| `amount` | number | Cost so far / pre-authorised amount (TBD) |
| `currency` | str | |
| `createdAt` | ISO datetime | |
| `isPaid` | bool | |
| `isStop` | bool | Stop requested / stopped |

### SessionProgress (socket `chargingSessionProgress`)

See [Real-time session progress](#real-time-session-progress-socketio) for the verified field table.

### Evse — charging point (nearby search **confirmed**; `GET /api/hubject/{evseId}` and `chargingStation` inferred)

Fields as returned by the nearby search. The station part is the Hubject OICP `EvseDataRecord`.

| Field | Type | Notes |
|---|---|---|
| `_id` | str | |
| `EvseID` | str | OICP EVSE ID, e.g. `IT*ABC*E123*1` (one connector) |
| `status` | str | `Available`, `Occupied`, `OutOfService`, `Unknown` |
| `isAvailable` | bool | Not consistent with `status` (false even when `Available`); prefer `status` |
| `distance` | number | Metres from the searched point (nearby search only) |
| `location` | GeoJSON Point | `coordinates: [lng, lat]` |
| `partner`, `Protocol` | str\|null | e.g. `HUBJECT` |
| `pricingDetails` | Pricing | Current tariff |
| `EvseData.OperatorID`, `EvseData.OperatorName` | str | |
| `EvseData.ChargingStationNames[]` | object | `{lang, value}` |
| `EvseData.Address` | object | `Street`, `HouseNum`, `City`, `PostalCode`, `Region`, `Country` (ISO alpha-3), … |
| `EvseData.GeoCoordinates.DecimalDegree` | object | `Latitude`, `Longitude` as strings |
| `EvseData.ChargingFacilities[]` | object | `Power` (kW), `PowerType` (`AC_1_PHASE`, `AC_3_PHASE`, `DC`), `Voltage`, `Amperage` |
| `EvseData.Plugs[]` | str | Connector types |
| `EvseData.AuthenticationModes[]`, `PaymentOptions[]`, `ValueAddedServices[]` | str | OICP enums |
| `EvseData.IsOpen24Hours`, `RenewableEnergy` | bool | |

### Pricing (tariff)

The fields up to `parkingPricing` are **confirmed** on the nearby search; the rest come from the app.

| Field | Type | Notes |
|---|---|---|
| `Price` | str (number) | Energy price paid with the EVDC wallet/tokens (= `pricingByType.TOKEN.Price`) |
| `Unit` | str | `kWh`; `DEFAULT` seen on some tariffs |
| `Currency` | str | |
| `BaseAmount`, `BaseCurrency`, `costKwh` | number / str | Operator's base price |
| `currentType` | str | `AC` / `DC` |
| `commissionPercent`, `PreAuthHoldAmount`, `isDefault` | number / bool | |
| `pricingByType.CARD`, `pricingByType.TOKEN` | object | Per payment method: `Price` (str), `CommissionPercent`, `restrictions`, `minPrice`, `maxPrice`. Card is usually a few cents higher. |
| `parkingPricing` | object | `IsEnabled`, `IsParkingFeeEnabled`, `ParkingFee`, `ParkingCap`, `MaxDurationInMinutes`, `MaxFee`, `Currency`, `exception`, `restrictions` |
| `restrictions` | object[] | Time-of-day / weekday / duration conditions |
| `flatPricing` | object | `IsEnabled`, `Fee`, `Currency`, `restrictions` (session fee) |
| `timePricing` | object | Overstay/time fee: `IsEnabled`, price, `exception` |
| `exception` | object | `type` (`skip` / `partial_skip`), `startTime`, `endTime` (not charged between) |
| `otherPricing[]` | Pricing | Alternative tariffs |
| `minPrice`, `maxPrice` | number | |

### Relationships

```
User ─1───N─ ChargingSession ─N───1─ Evse ─N───1─ Operator (OperatorID / OperatorName)
                 │   sessionId            │
                 │                        └─1───1─ Pricing (current tariff)
                 ├─1───1─ Receipt (PDF, by sessionId)
                 └─1───1─ Pricing snapshot (pricingDetails, tariff actually applied)

User ─1───N─ OngoingSession ─1───0..1─ SessionProgress (live, joined by sessionId)
                 │ evseId
                 └─N───1─ Evse
```

Notes:

- Live progress events carry both `SessionID` and `EvseID`; join them to the ongoing session by `sessionId`.
- `ChargingSession.pricingDetails` is a snapshot of the tariff used for billing. `Evse.pricing` is the current
  tariff and may have changed since.
- `sessionId` is shared by an ongoing session, its progress events and the history item it becomes when it ends
  (the history entry of the observed charge had the same `invoiceNo`).

## Out of scope

The app also calls endpoints for remote start/stop, connector unlock, wallet top-up, cards and RFID orders,
chat, reviews and bulk station sync (`/api/hubject/sync/evse`, `/api/hubject/stations/exclude-evses`).
They are deliberately not documented here (see the [scope](../README.md#scope)).

## Open questions

2. Check whether the backend requires `x-device-id` / `req-scope`, or if it validates the device id format.
3. Access token lifetime (the refresh token is not rotated).
4. Two-factor login (email OTP and TOTP): the verification endpoint and body are not identified yet.
5. Whether other stations report `Power` / `Current` in progress events (the observed one did not).
6. Whether a socket client must emit anything besides `register` (e.g. subscribe to a session).
7. Accounts linked to Google/Apple sign-in are refused by `/api/signIn-enc` even after setting a password
   (`400 "User is already register with social platform"`), although the app accepts the same credentials.
