# EVDC backend API

Notes on the interface between the official EVDC Android app and its backend, collected for interoperability
(see [LEGAL.md](../LEGAL.md)). Only what is needed to read the authenticated user's own data is documented here.

> Status: request shapes come from the decompiled client. Login, token refresh, profile, system configuration and
> the history / ongoing-session envelopes are **verified** against the real backend (2026-10-27, on an account with
> no charging history). Everything marked *inferred* still needs a real charging session to be confirmed.

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

`verifyOTP` is **verified** on a real account: a correct code returns HTTP 200 with the user and fresh session
tokens nested under `user`, a wrong code returns HTTP 400.

```json
{ "user": { "...user fields...", "accessToken": "…", "refreshToken": "…", "token": "…" },
  "message": "Verification code verified successfully." }
```

The TOTP endpoints are reconstructed from the app; their response is expected under `data` (not yet confirmed). The
client exposes `verify_two_factor()`, `verify_recovery_code()` and `resend_two_factor_code()`, and reads the tokens
from `user` or `data`.

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
fields are in [ChargingSession](#chargingsession--history-item-get-apihubjectcharge-history--data); they are
reconstructed from the app, as the probe account has no history yet.

### Receipt — `GET /api/hubject/download-pdf/{sessionId}`

Returns the session's PDF receipt as JSON `{ "base64", "filename" }` (from the app's handling; not yet seen live).

### Ongoing sessions — `GET /api/hubject/ongoing-sessionsV2`

No parameters. Returns the user's sessions that are currently in progress (the app's "ongoing sessions" screen, also
refreshed on pull-to-refresh and when a push notification arrives). Response schema: **to be captured**. The app
keys live data by `evseId`, so each ongoing session presumably carries one.

Session lifecycle states seen in the client: `SESSION_STARTED`, `SESSION_STOPPED`, `SESSION_PAID`, `SESSION_FAILED`.

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

`chargingSessionProgress` payload (field names read by the live session UI; they follow the Hubject OICP
`ChargingNotification` progress model, so `EvseID` and the other fields are PascalCase):

| Field | Meaning (UI label) |
|---|---|
| `evseId` / `EvseID` | EVSE the session is running on (required; events without it are dropped) |
| `SessionStart`, `ChargingStart` | Session / charging start timestamps |
| `Time` | Timestamp of the measurement |
| `Power`, `MaxPower` | Current and maximum power (kW) |
| `Current`, `MaxCurrent` | Current and maximum current (A) |
| `EnergyImport`, `EnergyExport` | Energy imported / exported (kWh) |
| `ConsumedEnergyProgress` | Energy delivered so far (kWh) |
| `ParkingTime`, `ReservationTime` | Parking and reservation time |
| `Timeline` | Series of past measurements (used for a sparkline) |

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

Used by the app's "near me" list. **Verified on 2026-10-27.**

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

**Verified against real responses on 2026-10-27** (fresh account, so session lists were empty). Envelopes are **not
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

> **Still inferred, not yet seen populated:** `ChargingSession` (history item), `OngoingSession`, the receipt PDF
> payload and the `Evse` detail — the probe account has no charging history. The field lists for these below come
> from the bytecode and must be confirmed against a real charge. A charging session on the probe account (or a
> capture from the phone) would fill this gap.

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

See [Real-time session progress](#real-time-session-progress-socketio). Fields: `EvseID`/`evseId`, `SessionStart`,
`ChargingStart`, `Time`, `Power`, `MaxPower`, `Current`, `MaxCurrent`, `EnergyImport`, `EnergyExport`,
`ConsumedEnergyProgress`, `ParkingTime`, `ReservationTime`, `Timeline[]`.

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

User ─1───N─ OngoingSession ─1───0..1─ SessionProgress (live, joined by evseId)
                 │ evseId
                 └─N───1─ Evse
```

Notes:

- Live progress is keyed by **`evseId`, not `sessionId`**, so two ongoing sessions on the same EVSE cannot be told
  apart from the progress event alone.
- `ChargingSession.pricingDetails` is a snapshot of the tariff used for billing. `Evse.pricing` is the current
  tariff and may have changed since.
- `sessionId` is presumably shared by an ongoing session and the history item it becomes when it ends
  (to verify).

## Out of scope

The app also calls endpoints for remote start/stop, connector unlock, wallet top-up, cards and RFID orders,
chat, reviews and bulk station sync (`/api/hubject/sync/evse`, `/api/hubject/stations/exclude-evses`).
They are deliberately not documented here (see the [scope](../README.md#scope)).

## Open questions

1. Confirm the `ChargingSession`, `OngoingSession`, receipt and `Evse` payloads with a real charging session.
2. Check whether the backend requires `x-device-id` / `req-scope`, or if it validates the device id format.
3. Access token lifetime (the refresh token is not rotated).
4. Two-factor login (email OTP and TOTP): the verification endpoint and body are not identified yet.
5. A real `chargingSessionProgress` event: types, units, how often events arrive.
6. Whether a socket client must emit anything besides `register` (e.g. subscribe to a session).
7. Accounts linked to Google/Apple sign-in are refused by `/api/signIn-enc` even after setting a password
   (`400 "User is already register with social platform"`), although the app accepts the same credentials.
